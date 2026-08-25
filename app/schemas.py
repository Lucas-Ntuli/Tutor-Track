from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, EmailStr, Field, field_validator

T = TypeVar("T")


class Page[T](BaseModel):
    """Generic pagination envelope so list endpoints don't return an
    unbounded array that gets slower and larger forever as a tenant
    grows - the kind of thing that's easy to skip in a demo project
    and then regret in production."""

    items: list[T]
    total: int
    limit: int
    offset: int


class StudentCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    guardian_email: EmailStr
    grade_level: str | None = Field(default=None, max_length=50)


class StudentOut(StudentCreate):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class SessionCreate(BaseModel):
    student_id: int
    tutor_id: int
    scheduled_at: datetime
    duration_minutes: int = Field(default=60, gt=0, le=480)

    @field_validator("scheduled_at")
    @classmethod
    def must_be_future(cls, value: datetime) -> datetime:
        # Naive datetimes are assumed UTC for this comparison; a real
        # product would require timezone-aware input and reject naive
        # ones outright.
        now = datetime.now(value.tzinfo) if value.tzinfo else datetime.utcnow()
        if value < now:
            raise ValueError("scheduled_at must be in the future")
        return value


class SessionOut(SessionCreate):
    id: int
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}