from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.core.database import Base

class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String, index=True, nullable=True)
    content = Column(Text, nullable=False)
    source_document = Column(String, nullable=True)
    page_number = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
