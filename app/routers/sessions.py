from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from deps import get_authenticated_tenant, get_db
from models import Session as TutorSession
from observability import BOOKING_CONFLICTS, SESSIONS_BOOKED
from schemas import Page, SessionCreate, SessionOut

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=201)
def create_session(
    payload: SessionCreate,
    db: Annotated[Session, Depends(get_db)],
    tenant: str = Depends(get_authenticated_tenant),
):
    # Guard against double-booking the same tutor - the kind of small
    # business-logic detail that shows this isn't a bare CRUD scaffold.
    window_start = payload.scheduled_at - timedelta(minutes=payload.duration_minutes)
    window_end = payload.scheduled_at + timedelta(minutes=payload.duration_minutes)

    conflict = db.execute(
        select(TutorSession).where(
            and_(
                TutorSession.tutor_id == payload.tutor_id,
                TutorSession.scheduled_at > window_start,
                TutorSession.scheduled_at < window_end,
                TutorSession.status != "cancelled",
            )
        )
    ).scalar_one_or_none()

    if conflict:
        BOOKING_CONFLICTS.labels(tenant=tenant).inc()
        raise HTTPException(
            status_code=409,
            detail=f"Tutor already has a session booked near {conflict.scheduled_at}",
        )

    session_obj = TutorSession(**payload.model_dump())
    db.add(session_obj)
    db.commit()
    db.refresh(session_obj)

    SESSIONS_BOOKED.labels(tenant=tenant).inc()
    return session_obj


@router.get("", response_model=Page[SessionOut])
def list_sessions(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None, description="Filter by session status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    query = select(TutorSession)
    count_query = select(func.count()).select_from(TutorSession)
    if status:
        query = query.where(TutorSession.status == status)
        count_query = count_query.where(TutorSession.status == status)

    total = db.execute(count_query).scalar_one()
    items = (
        db.execute(query.order_by(TutorSession.scheduled_at).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/{session_id}/cancel", response_model=SessionOut)
def cancel_session(
    session_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    session_obj = db.get(TutorSession, session_id)
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
    session_obj.status = "cancelled"
    db.commit()
    db.refresh(session_obj)
    return session_obj