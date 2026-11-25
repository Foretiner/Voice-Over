import os, uuid, json, asyncio
from dotenv import load_dotenv
load_dotenv()
from datetime import date
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from .db import init_db, get_session
from .schemas import BookRequest, CancelRequest
from . import services

app = FastAPI(title="VoiceCare API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[os.getenv("FRONTEND_ORIGIN","http://localhost:5173")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
CALL_EVENTS: dict[str, list[dict]] = {}


def append_call_event(call_id: str, event: dict):
    events = CALL_EVENTS.get(call_id)
    if events is not None:
        events.append(event)
        if len(events) > 500:
            del events[:-500]


@app.on_event("startup")
async def startup(): await init_db()

@app.get("/api/health")
async def health(): return {"status":"ok","service":"voicecare"}

@app.get("/api/doctors")
async def doctors(db: AsyncSession=Depends(get_session)): return await services.list_doctors(db)

@app.get("/api/slots")
async def slots(doctor_id: int|None=None, specialty: str|None=None, date: date|None=None, db: AsyncSession=Depends(get_session)):
    return await services.availability(db, doctor_id, specialty, date)

@app.get("/api/appointments")
async def get_appointments(db: AsyncSession=Depends(get_session)): return await services.appointments(db)

@app.post("/api/appointments/book")
async def book(req: BookRequest, db: AsyncSession=Depends(get_session)):
    try: return await services.book(db, req.doctor_id, req.slot_id, req.phone)
    except ValueError as e: raise HTTPException(400, str(e))

@app.post("/api/appointments/cancel")
async def cancel(req: CancelRequest, db: AsyncSession=Depends(get_session)):
    try: return await services.cancel(db, req.phone, req.appointment_id)
    except ValueError as e: raise HTTPException(404, str(e))

@app.post("/api/calls")
async def create_call():
    call_id = str(uuid.uuid4())
    CALL_EVENTS[call_id] = [{"type":"status","text":"Call session created"}]
    return {"call_id":call_id}

@app.get("/api/calls/{call_id}/events")
async def call_events(call_id: str, request: Request):
    async def stream():
        cursor = 0
        while not await request.is_disconnected():
            events = CALL_EVENTS.get(call_id, [])
            while cursor < len(events):
                yield f"data: {json.dumps(events[cursor])}\n\n"
                cursor += 1
            await asyncio.sleep(.35)
    return StreamingResponse(stream(), media_type="text/event-stream")

# Pipecat SmallWebRTC endpoint. Imported lazily so REST/demo mode works even
# when optional voice dependencies or credentials are not configured.
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCRequest, SmallWebRTCPatchRequest, SmallWebRTCRequestHandler
)
webrtc_handler = SmallWebRTCRequestHandler()

@app.post("/api/offer")
async def webrtc_offer(request: Request, call_id: str | None = None):
    if not (os.getenv("GEMINI_API_KEY") and os.getenv("ELEVENLABS_API_KEY") and os.getenv("ELEVENLABS_VOICE_ID")):
        raise HTTPException(503, "Add Gemini and ElevenLabs credentials to backend/.env before starting a voice call.")
    try:
        from .voice import run_bot
        offer = SmallWebRTCRequest.from_dict(await request.json())
        async def start_pipeline(connection):
            asyncio.create_task(run_bot(connection, call_id, append_call_event))
        return await webrtc_handler.handle_web_request(offer, start_pipeline)
    except Exception as exc:
        raise HTTPException(500, f"Could not establish WebRTC session: {exc}")

@app.patch("/api/offer")
async def webrtc_patch(request: Request):
    try:
        patch = SmallWebRTCPatchRequest(**(await request.json()))
        await webrtc_handler.handle_patch_request(patch)
        return {"status":"ok"}
    except Exception as exc:
        raise HTTPException(400, f"Could not apply ICE candidate update: {exc}")
