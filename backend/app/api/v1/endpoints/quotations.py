from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime, timedelta
import asyncio
import zipfile
from io import BytesIO

from app.core.database import get_db
from app.models.quotation import Quotation, QuotationStatus, QuotationData
from app.schemas.quotation import (
    QuotationCreate,
    QuotationResponse,
    QuotationStatusResponse,
    QuotationDetailResponse,
    QuotationDataResponse
)
from app.agents.orchestrator import AgentOrchestrator
from app.services.pdf_generator import PDFGenerator
from app.services.excel_generator import ExcelGenerator
from app.core.exceptions import QuotationNotFoundError, QuotationNotCompletedError
from app.utils.validators import (
    validate_project_description,
    validate_zip_code,
    validate_project_type
)

router = APIRouter()
orchestrator = AgentOrchestrator()
pdf_generator = PDFGenerator()
excel_generator = ExcelGenerator()


@router.post("/", response_model=QuotationResponse, status_code=status.HTTP_201_CREATED)
async def create_quotation(
    quotation: QuotationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create a new quotation request"""
    # Validate input
    is_valid, error_msg = validate_project_description(quotation.project_description)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    is_valid, error_msg = validate_zip_code(quotation.zip_code)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    is_valid, error_msg = validate_project_type(quotation.project_type)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    quotation_id = f"quot-{uuid.uuid4().hex[:12]}"
    
    db_quotation = Quotation(
        id=quotation_id,
        project_description=quotation.project_description,
        location=quotation.location,
        zip_code=quotation.zip_code,
        project_type=quotation.project_type,
        timeline=quotation.timeline,
        status=QuotationStatus.PENDING
    )
    
    db.add(db_quotation)
    db.commit()
    db.refresh(db_quotation)
    
    # Start processing in background
    background_tasks.add_task(process_quotation_background, quotation_id)
    
    return db_quotation


async def process_quotation_background(quotation_id: str):
    """Background task to process quotation"""
    # Create new session for background task
    from app.core.database import SessionLocal
    background_db = SessionLocal()
    try:
        await orchestrator.process_quotation(quotation_id, background_db)
    finally:
        background_db.close()


@router.get("/{quotation_id}", response_model=QuotationDetailResponse)
async def get_quotation(
    quotation_id: str,
    include_data: bool = True,
    db: Session = Depends(get_db)
):
    """Get quotation by ID with optional data"""
    quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not quotation:
        raise QuotationNotFoundError(quotation_id)
    
    quotation_data = None
    if include_data:
        quotation_data_obj = db.query(QuotationData).filter(
            QuotationData.quotation_id == quotation_id
        ).first()
        if quotation_data_obj:
            quotation_data = QuotationDataResponse(
                quotation_id=quotation_data_obj.quotation_id,
                extracted_data=quotation_data_obj.extracted_data,
                confidence_score=quotation_data_obj.confidence_score,
                cost_breakdown=quotation_data_obj.cost_breakdown,
                total_cost=quotation_data_obj.total_cost
            )
    
    response = QuotationDetailResponse(
        id=quotation.id,
        project_description=quotation.project_description,
        location=quotation.location,
        zip_code=quotation.zip_code,
        project_type=quotation.project_type,
        timeline=quotation.timeline,
        status=quotation.status,
        created_at=quotation.created_at,
        updated_at=quotation.updated_at,
        quotation_data=quotation_data
    )
    
    return response


@router.get("/{quotation_id}/status", response_model=QuotationStatusResponse)
async def get_quotation_status(
    quotation_id: str,
    db: Session = Depends(get_db)
):
    """Get quotation status and progress"""
    quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not quotation:
        raise QuotationNotFoundError(quotation_id)
    
    # Map status to stage name
    stage_map = {
        QuotationStatus.PENDING: None,
        QuotationStatus.PROCESSING: "initializing",
        QuotationStatus.DATA_COLLECTION: "data_collection",
        QuotationStatus.COST_CALCULATION: "cost_calculation",
        QuotationStatus.COMPLETED: "completed",
        QuotationStatus.FAILED: "failed"
    }
    
    # Calculate progress based on status
    progress_map = {
        QuotationStatus.PENDING: 0,
        QuotationStatus.PROCESSING: 10,
        QuotationStatus.DATA_COLLECTION: 30,
        QuotationStatus.COST_CALCULATION: 70,
        QuotationStatus.COMPLETED: 100,
        QuotationStatus.FAILED: 0
    }
    
    # Estimate completion time
    estimated_completion = None
    if quotation.status not in [QuotationStatus.COMPLETED, QuotationStatus.FAILED]:
        estimated_completion = datetime.utcnow() + timedelta(minutes=2)
    
    return QuotationStatusResponse(
        quotation_id=quotation.id,
        status=quotation.status,
        current_stage=stage_map.get(quotation.status),
        progress=progress_map.get(quotation.status, 0),
        estimated_completion=estimated_completion,
        last_update=quotation.updated_at or quotation.created_at
    )


@router.get("/{quotation_id}/download")
async def download_quotation(
    quotation_id: str,
    format: str = "pdf",
    db: Session = Depends(get_db)
):
    """
    Download quotation in specified format.
    
    Formats:
    - pdf: Download as PDF file
    - excel: Download as Excel file
    - both: Download as ZIP containing both PDF and Excel
    
    Example: /api/v1/quotations/{id}/download?format=pdf
    """
    # Validate quotation exists
    quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not quotation:
        raise QuotationNotFoundError(quotation_id)
    
    if quotation.status != QuotationStatus.COMPLETED:
        raise QuotationNotCompletedError(quotation_id, quotation.status.value)
    
    quotation_data = db.query(QuotationData).filter(
        QuotationData.quotation_id == quotation_id
    ).first()
    
    # Normalize format to lowercase
    format = format.lower()
    
    if format == "pdf":
        # Generate PDF
        pdf_buffer = pdf_generator.generate_quotation_pdf(quotation, quotation_data)
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=quotation_{quotation_id}.pdf"
            }
        )
    
    elif format == "excel":
        # Generate Excel
        excel_buffer = excel_generator.generate_quotation_excel(quotation, quotation_data)
        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=quotation_{quotation_id}.xlsx"
            }
        )
    
    elif format == "both":
        # Generate both files
        pdf_buffer = pdf_generator.generate_quotation_pdf(quotation, quotation_data)
        excel_buffer = excel_generator.generate_quotation_excel(quotation, quotation_data)
        
        # Create ZIP file
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(f"quotation_{quotation_id}.pdf", pdf_buffer.read())
            zip_file.writestr(f"quotation_{quotation_id}.xlsx", excel_buffer.read())
        
        zip_buffer.seek(0)
        
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=quotation_{quotation_id}.zip"
            }
        )
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Use 'pdf', 'excel', or 'both'"
        )


@router.get("/", response_model=List[QuotationResponse])
async def list_quotations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all quotations"""
    quotations = db.query(Quotation).offset(skip).limit(limit).all()
    return quotations
