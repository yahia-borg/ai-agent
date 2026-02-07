from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError, field_validator
from typing import List, Dict, Any, Optional, Union
from sqlalchemy.orm import Session
import json
import asyncio
import uuid
import logging

from app.core.database import get_db
from app.agents.conversational_agent import ConversationalAgent

logger = logging.getLogger(__name__)

router = APIRouter()


@router.options("")
async def chat_options():
    """Handle CORS preflight for chat endpoint"""
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = []  # Use Any to be more flexible, then validate
    session_id: Optional[str] = None
    quotation_id: Optional[str] = None
    
    @field_validator('history', mode='before')
    @classmethod
    def validate_history(cls, v):
        """Normalize history to ensure proper format"""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        # Normalize each history item
        normalized = []
        for item in v:
            if isinstance(item, dict):
                # Extract only role and content, ensure they're strings
                role = item.get('role', '')
                content = item.get('content', '')
                if role in ['user', 'assistant']:
                    normalized.append({
                        'role': str(role),
                        'content': str(content) if content is not None else ''
                    })
        return normalized
    
    class Config:
        # Allow extra fields but ignore them during validation
        extra = "ignore"


class ChatResponse(BaseModel):
    response: str
    quotation_id: Optional[str] = None
    history: List[Dict[str, str]]


@router.post("", response_model=ChatResponse)
async def chat_endpoint(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Chat endpoint that handles text messages and file uploads.
    Supports both regular JSON and multipart/form-data for file uploads.
    """
    try:
        content_type = request.headers.get("content-type", "")
        
        # Check if it's multipart/form-data (file upload)
        if "multipart/form-data" in content_type:
            form = await request.form()
            message = form.get("message", "")
            history_str = form.get("history")
            session_id = form.get("session_id")
            quotation_id = form.get("quotation_id")
            files = form.getlist("files") if "files" in form else []
            
            # Parse history
            parsed_history = []
            if history_str:
                try:
                    parsed_history = json.loads(history_str)
                except json.JSONDecodeError:
                    parsed_history = []
            
            # Process files
            file_data = []
            for file in files:
                if hasattr(file, 'read'):
                    content = await file.read()
                    file_data.append({
                        "name": file.filename,
                        "content": content,
                        "content_type": file.content_type
                    })
        else:
            # JSON request
            body = await request.json()
            message = body.get("message", "")
            parsed_history = body.get("history", [])
            session_id = body.get("session_id")
            quotation_id = body.get("quotation_id")
            file_data = []
        
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Initialize agent (LangGraph's MemorySaver handles conversation persistence)
        agent = ConversationalAgent()
        
        # Get or create session_id (separate from quotation_id)
        if not session_id:
            session_id = f"session-{uuid.uuid4().hex[:12]}"
        
        # Process message with agent
        result = await agent.process_message(
            message=message,
            history=parsed_history,
            session_id=session_id,
            quotation_id=quotation_id,
            files=file_data,
            db=db
        )
        
        return ChatResponse(
            response=result.get("response", ""),
            quotation_id=result.get("quotation_id", quotation_id),
            history=result.get("history", [])
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.options("/stream")
async def chat_stream_options():
    """Handle CORS preflight for stream endpoint"""
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )


@router.post("/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Server-Sent Events (SSE) streaming endpoint for real-time agent responses.
    """
    logger.info(f"Stream endpoint called with message length: {len(request.message) if request.message else 0}, history length: {len(request.history) if request.history else 0}")
    
    # Validate request
    if not request.message or not request.message.strip():
        async def error_generator():
            error_chunk = {
                "type": "error",
                "content": "Message is required and cannot be empty"
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
        return StreamingResponse(
            error_generator(),
            media_type="text/event-stream",
            status_code=400
        )
    
    # Validate history format
    if request.history is not None:
        if not isinstance(request.history, list):
            logger.warning(f"Invalid history format: expected list, got {type(request.history)}")
            request.history = []
        else:
            # Validate each history item has required fields
            validated_history = []
            for idx, item in enumerate(request.history):
                if isinstance(item, dict):
                    # Ensure only role and content are present (strip any extra fields)
                    if "role" in item and "content" in item:
                        # Validate role is valid
                        if item["role"] not in ["user", "assistant"]:
                            logger.warning(f"Invalid role in history item {idx}: {item.get('role')}")
                            continue
                        # Ensure content is a string
                        if not isinstance(item["content"], str):
                            logger.warning(f"Invalid content type in history item {idx}: {type(item.get('content'))}")
                            item["content"] = str(item["content"])
                        validated_history.append({
                            "role": item["role"],
                            "content": item["content"]
                        })
                    else:
                        logger.warning(f"Invalid history item format at index {idx}: missing role or content, item: {item}")
                else:
                    logger.warning(f"Invalid history item type at index {idx}: expected dict, got {type(item)}")
            request.history = validated_history
            logger.info(f"Validated history: {len(validated_history)} items")
    
    async def event_generator():
        try:
            # LangGraph's MemorySaver handles conversation persistence automatically
            agent = ConversationalAgent()
            
            # Get or create session_id (separate from quotation_id)
            session_id = request.session_id or f"session-{uuid.uuid4().hex[:12]}"
            
            logger.info(f"Processing streaming message for session: {session_id}, history length: {len(request.history or [])}")
            
            # Process message with streaming
            async for chunk in agent.process_message_stream(
                message=request.message,
                history=request.history or [],
                session_id=session_id,
                quotation_id=request.quotation_id,
                db=db
            ):
                yield f"data: {json.dumps(chunk)}\n\n"
            
            # Agent already sends 'done' event with quotation_id/session_id
            pass
            
        except ValidationError as e:
            logger.error(f"Validation error in streaming endpoint: {e}")
            error_chunk = {
                "type": "error",
                "content": f"Validation error: {str(e)}"
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
        except Exception as e:
            logger.error(f"Error in streaming endpoint: {e}", exc_info=True)
            error_chunk = {
                "type": "error",
                "content": f"An error occurred: {str(e)}"
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

