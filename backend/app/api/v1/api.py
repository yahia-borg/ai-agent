from fastapi import APIRouter
from app.api.v1.endpoints import quotations, questions, chat, admin

api_router = APIRouter()
api_router.include_router(quotations.router, prefix="/quotations", tags=["quotations"])
api_router.include_router(questions.router, prefix="/quotations", tags=["quotations", "questions"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
