"""
models.py

Domain model for a tutoring center: students, tutors, and scheduled
sessions. Deliberately real-domain rather than generic "Item" tables,
since that's part of what makes this project read as a product rather
than a CRUD scaffold.

created_at/updated_at on every table isn't decoration - it's the
minimum an on-call engineer needs to answer "when did this row appear"
during an incident, and indexes on the columns actually used to filter
(tutor_id + scheduled_at for conflict checks) keep that query fast as
a tenant's session history grows.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, DateTime, Numeric, Index, func


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    guardian_email: Mapped[str] = mapped_column(String(200), index=True)
    grade_level: Mapped[str] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow
    )

    sessions: Mapped[list["Session"]] = relationship(back_populates="student")


class Tutor(Base):
    __tablename__ = "tutors"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    subject_specialty: Mapped[str] = mapped_column(String(100))
    hourly_rate: Mapped[float] = mapped_column(Numeric(6, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow
    )

    sessions: Mapped[list["Session"]] = relationship(back_populates="tutor")


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        # Speeds up exactly the query create_session() runs to check
        # for double-bookings - without it, that check degrades to a
        # full table scan as a tenant's history grows.
        Index("ix_sessions_tutor_scheduled", "tutor_id", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    tutor_id: Mapped[int] = mapped_column(ForeignKey("tutors.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    duration_minutes: Mapped[int] = mapped_column(default=60)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow
    )

    student: Mapped["Student"] = relationship(back_populates="sessions")
    tutor: Mapped["Tutor"] = relationship(back_populates="sessions")