"""
Consolidated session/quotation resolution utility.
Replaces duplicated resolution logic in tools_wrapper.py
(resolve_quotation, collect_project_data, calculate_costs).
"""
import uuid
import logging
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quotation import Quotation
from app.models.memory import AgentSession

logger = logging.getLogger(__name__)


async def resolve_quotation_id(
    quotation_id: str,
    db: AsyncSession,
    create_if_missing: bool = True,
    additional_info: Optional[str] = None,
) -> Tuple[Optional[Quotation], bool]:
    """
    Resolve a quotation_id (which may be a session-id) to a Quotation object.

    Logic:
    1. Try direct lookup by quotation_id
    2. If not found and quotation_id starts with 'session-', resolve via AgentSession
    3. If still not found and create_if_missing is True, create new Quotation and link to session

    Args:
        quotation_id: Quotation ID or session ID (pattern: "session-*")
        db: Async database session
        create_if_missing: Whether to auto-create if not found
        additional_info: Optional description for new quotations

    Returns:
        Tuple of (Quotation or None, was_created: bool)
    """
    # Step 1: Direct lookup
    result = await db.execute(select(Quotation).filter(Quotation.id == quotation_id))
    quotation = result.scalar_one_or_none()

    real_session_id = None

    # Step 2: Session resolution
    if not quotation and quotation_id.startswith("session-"):
        real_session_id = quotation_id
        session_result = await db.execute(
            select(AgentSession).filter(AgentSession.session_id == real_session_id)
        )
        session = session_result.scalar_one_or_none()
        if session and session.quotation_id:
            quote_result = await db.execute(
                select(Quotation).filter(Quotation.id == session.quotation_id)
            )
            quotation = quote_result.scalar_one_or_none()

    # Step 3: Auto-create
    if not quotation and create_if_missing:
        logger.info(f"Quotation not found for '{quotation_id}'. Creating new quotation.")
        new_quotation_id = str(uuid.uuid4())
        quotation = Quotation(
            id=new_quotation_id,
            project_description=additional_info or "New construction project",
            status="pending"
        )
        db.add(quotation)
        await db.commit()
        await db.refresh(quotation)

        # Link to session if we detected a session_id
        if real_session_id:
            try:
                session_result = await db.execute(
                    select(AgentSession).filter(AgentSession.session_id == real_session_id)
                )
                session = session_result.scalar_one_or_none()
                if not session:
                    session = AgentSession(
                        session_id=real_session_id,
                        quotation_id=None,
                        session_data={"conversation_history": []}
                    )
                    db.add(session)
                session.quotation_id = new_quotation_id
                await db.commit()
                await db.refresh(session)
                logger.info(f"Linked new quotation {new_quotation_id} to session {real_session_id}")
            except Exception as e:
                logger.warning(f"Failed to link quotation to session: {e}")

        return quotation, True

    if quotation and not create_if_missing:
        return quotation, False

    if quotation:
        # Update description if additional info provided (avoid duplicates)
        if additional_info:
            current_desc = quotation.project_description or ""
            # Only append if this info isn't already in the description
            if additional_info.strip() not in current_desc:
                # Limit total description length to prevent bloat
                new_desc = f"{current_desc}  Client Update: {additional_info}".strip()
                if len(new_desc) > 2000:
                    # Keep only the latest update + a trimmed base
                    base = current_desc[:500] if len(current_desc) > 500 else current_desc
                    new_desc = f"{base}  Client Update: {additional_info}".strip()
                quotation.project_description = new_desc
                await db.commit()
        return quotation, False

    return None, False
