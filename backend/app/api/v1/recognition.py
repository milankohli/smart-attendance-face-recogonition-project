"""
app/api/v1/recognition.py
───────────────────────────────────────────────────────────────────────────────
Real-time face recognition endpoint.

Accepts a single image frame (multipart upload), runs the full
recognition pipeline (detect → embed → nearest-neighbour → threshold →
attendance mark), and returns a structured RecognitionResponse.

No WebSocket; polling-based or one-shot HTTP only.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_async_session
from app.models.attendance import ConfidenceBand
from app.models.user import User
from app.services.attendance_service import AttendanceService

router = APIRouter(prefix="/recognition", tags=["Recognition"])


class RecognitionResponse(BaseModel):
    """HTTP-safe representation of AttendanceService.process_frame() output."""

    recognized: bool
    student_id: int | None = None
    student_name: str | None = None
    student_code: str | None = None
    similarity: float
    confidence_band: ConfidenceBand
    already_marked: bool = False
    attendance_record_id: int | None = None
    message: str


def _get_service(session: AsyncSession = Depends(get_async_session)) -> AttendanceService:
    return AttendanceService(session)


@router.post("/identify", response_model=RecognitionResponse)
async def identify_frame(
    image: UploadFile = File(..., description="JPEG/PNG frame to identify"),
    device_id: str | None = Query(default=None, description="Optional camera/kiosk identifier"),
    svc: AttendanceService = Depends(_get_service),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> RecognitionResponse:
    """
    Run the recognition pipeline on a single uploaded frame.

    1. Decode the uploaded image to a BGR numpy array.
    2. Detect face crop → generate 512-D embedding.
    3. pgvector nearest-neighbour → cosine similarity threshold.
    4. If recognised and not already marked today, insert an attendance record.
    5. Return a structured result including student info, similarity, and
       whether attendance was freshly marked.

    `already_marked=True` when the student was recognised but had already
    been marked present today (mirrors the desktop app's duplicate guard).
    """
    raw = await image.read()
    arr = np.frombuffer(raw, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not decode uploaded image. Provide a valid JPEG or PNG.",
        )

    result = await svc.process_frame(frame, device_id=device_id)
    await session.commit()

    student = result.student
    already_marked = result.already_marked

    return RecognitionResponse(
        recognized=result.recognized,
        student_id=student.id if student else None,
        student_name=student.name if student else None,
        student_code=student.student_code if student else None,
        similarity=result.similarity,
        confidence_band=result.confidence_band,
        already_marked=already_marked,
        message=result.message,
    )
