from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any

from app.core.database import get_db
from app.models.quotation import Quotation, QuotationStatus
from app.models.quotation import QuotationData

router = APIRouter()


class QuestionAnswer(BaseModel):
    question_id: str
    answer: Any


class QuestionAnswers(BaseModel):
    question_set_id: str
    answers: Dict[str, Any]
    additional_notes: str = ""


@router.post("/{quotation_id}/questions")
async def submit_question_answers(
    quotation_id: str,
    answers: QuestionAnswers,
    db: Session = Depends(get_db)
):
    """Submit answers to agent questions"""
    quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not quotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quotation {quotation_id} not found"
        )
    
    # Get quotation data
    quotation_data = db.query(QuotationData).filter(
        QuotationData.quotation_id == quotation_id
    ).first()
    
    if not quotation_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quotation data for {quotation_id} not found"
        )
    
    # Update extracted data with answers
    if not quotation_data.extracted_data:
        quotation_data.extracted_data = {}
    
    # Merge answers into extracted data
    quotation_data.extracted_data.update(answers.answers.dict())
    
    if answers.additional_notes:
        quotation_data.extracted_data["additional_notes"] = answers.additional_notes
    
    db.commit()
    
    return {
        "status": "accepted",
        "message": "Answers submitted successfully",
        "quotation_id": quotation_id
    }

