"""
Session management service for handling conversation sessions and quotation linking.
"""
from sqlalchemy.orm import Session
from app.models.memory import AgentSession
from app.models.quotation import Quotation
from typing import Optional
import logging
import uuid

logger = logging.getLogger(__name__)


class SessionService:
    """Manages conversation sessions and their linkage to quotations."""

    @staticmethod
    def get_or_create_session(db: Session, session_id: str) -> AgentSession:
        """
        Get existing session or create new one.

        Args:
            db: Database session
            session_id: Unique session identifier

        Returns:
            AgentSession instance
        """
        session = db.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if not session:
            session = AgentSession(
                session_id=session_id,
                quotation_id=None,  # Will be set when quotation is created
                session_data={"conversation_history": []}
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            logger.info(f"Created new session: {session_id}")

        return session

    @staticmethod
    def link_session_to_quotation(
        db: Session,
        session_id: str,
        quotation_id: str
    ) -> AgentSession:
        """
        Link a session to a quotation.

        Args:
            db: Database session
            session_id: Session identifier
            quotation_id: Quotation identifier

        Returns:
            Updated AgentSession instance

        Raises:
            ValueError: If quotation doesn't exist
        """
        session = SessionService.get_or_create_session(db, session_id)

        # Verify quotation exists
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not quotation:
            raise ValueError(f"Quotation {quotation_id} not found")

        session.quotation_id = quotation_id
        db.commit()
        db.refresh(session)

        logger.info(f"Linked session {session_id} to quotation {quotation_id}")
        return session

    @staticmethod
    def get_session_quotation(db: Session, session_id: str) -> Optional[Quotation]:
        """
        Get the quotation associated with a session.

        Args:
            db: Database session
            session_id: Session identifier

        Returns:
            Quotation instance if linked, None otherwise
        """
        session = db.query(AgentSession).filter(
            AgentSession.session_id == session_id
        ).first()

        if session and session.quotation_id:
            return session.quotation

        return None

    @staticmethod
    def create_new_quotation_for_session(
        db: Session,
        session_id: str,
        project_description: str = "New construction project"
    ) -> Quotation:
        """
        Create a new quotation and link it to the session.

        Args:
            db: Database session
            session_id: Session identifier
            project_description: Description of the project

        Returns:
            Newly created Quotation instance
        """
        from app.models.quotation import QuotationStatus

        # Create quotation with proper UUID
        quotation = Quotation(
            id=str(uuid.uuid4()),
            project_description=project_description,
            status=QuotationStatus.PENDING
        )
        db.add(quotation)
        db.commit()
        db.refresh(quotation)

        # Link session to quotation
        SessionService.link_session_to_quotation(db, session_id, quotation.id)

        logger.info(f"Created quotation {quotation.id} for session {session_id}")
        return quotation

    @staticmethod
    def update_session_data(
        db: Session,
        session_id: str,
        session_data: dict
    ) -> AgentSession:
        """
        Update session data.

        Args:
            db: Database session
            session_id: Session identifier
            session_data: New session data to save

        Returns:
            Updated AgentSession instance
        """
        session = SessionService.get_or_create_session(db, session_id)
        session.session_data = session_data
        db.commit()
        db.refresh(session)

        logger.debug(f"Updated session data for {session_id}")
        return session
