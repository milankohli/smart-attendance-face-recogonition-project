"""
app/websocket/recognition_ws.py
───────────────────────────────────────────────────────────────────────────────
WebSocket endpoint for real-time face recognition and attendance marking.

Protocol
────────
The client opens a WebSocket to:
    ws://<host>/ws/recognition?token=<jwt_access_token>&device_id=<optional>

Frame → Server (binary):
    Raw JPEG or PNG bytes of a single video frame. The client sends frames
    at whatever rate it chooses (typically 5–15 fps). Frames received while
    the previous one is still being processed are queued and processed in
    order; if the queue fills up, the oldest unprocessed frame is dropped
    (backpressure handling).

Server → Client (text / JSON):
    Every frame processed produces exactly one JSON message:

    {
      "event":            "no_face" | "unknown" | "already_marked" | "marked" | "error",
      "recognized":       bool,
      "student_id":       int | null,
      "student_name":     str | null,
      "student_code":     str | null,
      "similarity":       float,
      "confidence_band":  "high" | "medium" | "low",
      "already_marked":   bool,
      "attendance_id":    int | null,
      "message":          str,
      "processed_at":     ISO-8601 UTC timestamp
    }

    Additionally, the server sends a periodic keepalive ping every
    KEEPALIVE_INTERVAL_S seconds when idle:
    { "event": "ping", "processed_at": "..." }

Authentication
──────────────
JWT is passed as a query-parameter `token` rather than in the
`Authorization` header because the browser WebSocket API does not allow
custom headers. The token is validated before the handshake is accepted;
the connection is closed with 4001 if invalid or 4003 if the user is
inactive.

Backpressure / concurrency
──────────────────────────
A single asyncio.Queue (max FRAME_QUEUE_SIZE) decouples frame receipt
from the heavyweight recognition pipeline (FaceDetector + FaceNet + DB).
This ensures the receive loop is never blocked by inference latency, while
still processing every enqueued frame in the order it was received. Frames
that arrive when the queue is full are silently dropped (logged at DEBUG).

Lifecycle
─────────
1. Client connects → JWT validated → session + service created.
2. Receiver coroutine puts frames into the queue.
3. Processor coroutine pulls frames, runs the pipeline, sends JSON results.
4. Keepalive coroutine sends pings while the queue is idle.
5. On disconnect or any unhandled exception the DB session is rolled back
   and closed, the queue is drained, and both coroutines are cancelled.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decode_token
from app.db.session import AsyncSessionLocal
from app.repositories.user_repo import UserRepository
from app.services.attendance_service import AttendanceService

log = get_logger(__name__)

router = APIRouter()

# ── Tunable constants ─────────────────────────────────────────────────────────
FRAME_QUEUE_SIZE = 4          # max buffered frames; extras are dropped
KEEPALIVE_INTERVAL_S = 15     # seconds between idle pings
CLOSE_INVALID_TOKEN = 4001    # custom WS close code: auth failure
CLOSE_INACTIVE_USER = 4003    # custom WS close code: account disabled


# ── Helper: build a JSON result payload ──────────────────────────────────────

def _result_payload(
    event: str,
    *,
    recognized: bool = False,
    student_id: int | None = None,
    student_name: str | None = None,
    student_code: str | None = None,
    similarity: float = 0.0,
    confidence_band: str = "low",
    already_marked: bool = False,
    attendance_id: int | None = None,
    message: str = "",
) -> str:
    return json.dumps(
        {
            "event": event,
            "recognized": recognized,
            "student_id": student_id,
            "student_name": student_name,
            "student_code": student_code,
            "similarity": round(similarity, 6),
            "confidence_band": confidence_band,
            "already_marked": already_marked,
            "attendance_id": attendance_id,
            "message": message,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def _ping_payload() -> str:
    return json.dumps({"event": "ping", "processed_at": datetime.now(timezone.utc).isoformat()})


def _error_payload(message: str) -> str:
    return _result_payload("error", message=message)


# ── Authentication helper ─────────────────────────────────────────────────────

async def _authenticate(
    websocket: WebSocket,
    token: str | None,
    session: AsyncSession,
) -> bool:
    """
    Validate `token` (JWT access token) and verify the user is active.

    Closes the WebSocket with an appropriate code on failure.
    Returns True on success, False otherwise.
    """
    if not token:
        await websocket.close(code=CLOSE_INVALID_TOKEN, reason="Missing token.")
        return False

    try:
        claims = decode_token(token)
    except JWTError:
        await websocket.close(code=CLOSE_INVALID_TOKEN, reason="Invalid or expired token.")
        return False

    if claims.get("type") != "access":
        await websocket.close(code=CLOSE_INVALID_TOKEN, reason="Token is not an access token.")
        return False

    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError):
        await websocket.close(code=CLOSE_INVALID_TOKEN, reason="Malformed token subject.")
        return False

    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        await websocket.close(code=CLOSE_INVALID_TOKEN, reason="User not found.")
        return False
    if not user.is_active:
        await websocket.close(code=CLOSE_INACTIVE_USER, reason="User account is disabled.")
        return False

    return True


# ── Frame processor ───────────────────────────────────────────────────────────

async def _process_frame(
    raw: bytes,
    svc: AttendanceService,
    session: AsyncSession,
    device_id: str | None,
) -> str:
    """
    Run the full recognition pipeline on raw image bytes.

    Returns a JSON string to send back to the client.
    """
    # Decode image bytes → BGR numpy array
    arr = np.frombuffer(raw, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return _error_payload("Could not decode frame — send a valid JPEG or PNG.")

    # Run detection → embedding → NN search → threshold → attendance mark
    result = await svc.process_frame(frame, device_id=device_id)
    await session.commit()

    student = result.student
    already_marked = result.already_marked
    recognized = result.recognized

    # Map to event label
    if result.blocked_by_policy:
        event = "error"
    elif not recognized and result.similarity == 0.0:
        event = "no_face"
    elif not recognized:
        event = "unknown"
    elif already_marked:
        event = "already_marked"
    elif result.attendance_marked:
        event = "marked"
    else:
        event = "unknown"

    return _result_payload(
        event,
        recognized=recognized,
        student_id=student.id if student else None,
        student_name=student.name if student else None,
        student_code=student.student_code if student else None,
        similarity=result.similarity,
        confidence_band=result.confidence_band.value,
        already_marked=already_marked,
        message=result.message,
    )


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/recognition")
async def recognition_ws(
    websocket: WebSocket,
    token: str | None = None,
    device_id: str | None = None,
) -> None:
    """
    WebSocket endpoint for real-time face recognition.

    Query parameters:
        token     : JWT access token (required — browser WS API has no headers).
        device_id : Optional camera / kiosk identifier logged with each record.

    Binary messages from the client are treated as raw image frames (JPEG/PNG).
    Text messages are silently ignored (reserved for future control messages).
    """
    # ── Accept & authenticate ─────────────────────────────────────────────
    await websocket.accept()

    session: AsyncSession = AsyncSessionLocal()
    try:
        authenticated = await _authenticate(websocket, token, session)
        if not authenticated:
            return  # connection already closed inside _authenticate

        svc = AttendanceService(session)
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=FRAME_QUEUE_SIZE)
        log.info(
            "WebSocket recognition session started",
            extra={"ctx_device_id": device_id},
        )

        # ── Coroutine: receive frames from client → queue ─────────────────
        async def _receiver() -> None:
            try:
                while True:
                    message = await websocket.receive()

                    if message["type"] == "websocket.disconnect":
                        break

                    raw: bytes | None = None
                    if "bytes" in message and message["bytes"]:
                        raw = message["bytes"]
                    elif "text" in message and message["text"]:
                        # Text frames reserved for future control messages
                        log.debug(
                            "WS text frame ignored",
                            extra={"ctx_device_id": device_id},
                        )
                        continue

                    if raw is None:
                        continue

                    if queue.full():
                        # Drop oldest frame to make room (newest frame wins)
                        try:
                            queue.get_nowait()
                            log.debug(
                                "Frame queue full — oldest frame dropped",
                                extra={"ctx_device_id": device_id},
                            )
                        except asyncio.QueueEmpty:
                            pass

                    await queue.put(raw)

            except WebSocketDisconnect:
                pass

        # ── Coroutine: process frames from queue → send results ────────────
        async def _processor() -> None:
            while True:
                try:
                    raw = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL_S)
                except asyncio.TimeoutError:
                    # Queue idle → send keepalive ping
                    try:
                        await websocket.send_text(_ping_payload())
                    except Exception:
                        break
                    continue

                try:
                    payload = await _process_frame(raw, svc, session, device_id)
                    await websocket.send_text(payload)
                except WebSocketDisconnect:
                    break
                except Exception as exc:
                    log.exception(
                        "Error processing WS frame",
                        extra={"ctx_device_id": device_id, "ctx_error": str(exc)},
                    )
                    try:
                        await websocket.send_text(_error_payload(f"Internal error: {exc}"))
                    except Exception:
                        break
                finally:
                    queue.task_done()

        # ── Run both coroutines concurrently; cancel both on any exit ──────
        receiver_task = asyncio.create_task(_receiver())
        processor_task = asyncio.create_task(_processor())

        done, pending = await asyncio.wait(
            {receiver_task, processor_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    except WebSocketDisconnect:
        log.info(
            "WebSocket client disconnected",
            extra={"ctx_device_id": device_id},
        )
    except Exception as exc:
        log.exception(
            "Unhandled WebSocket error",
            extra={"ctx_device_id": device_id, "ctx_error": str(exc)},
        )
        try:
            await websocket.send_text(_error_payload(f"Server error: {exc}"))
            await websocket.close()
        except Exception:
            pass
    finally:
        await session.rollback()
        await session.close()
        log.info(
            "WebSocket recognition session ended",
            extra={"ctx_device_id": device_id},
        )
