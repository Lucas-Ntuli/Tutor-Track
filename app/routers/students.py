from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deps import get_db
from models import Student
from schemas import Page, StudentCreate, StudentOut

router = APIRouter(prefix="/students", tags=["students"])


@router.post("", response_model=StudentOut, status_code=201)
def create_student(
    payload: StudentCreate,
    db: Annotated[Session, Depends(get_db)],
):
    student = Student(**payload.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("", response_model=Page[StudentOut])
def list_students(
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    total = db.execute(select(func.count()).select_from(Student)).scalar_one()
    items = (
        db.execute(select(Student).order_by(Student.id).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{student_id}", response_model=StudentOut)
def get_student(
    student_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student