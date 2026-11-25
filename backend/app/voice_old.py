import os, re
from datetime import date
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.aggregators.llm_context import LLMContext, LLMContextAggregatorPair
from pipecat.services.elevenlabs.stt import ElevenLabsSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport, SmallWebRTCParams
from .db import SessionLocal
from . import services

SYSTEM_PROMPT = """You are VoiceCare, a friendly doctor appointment booking assistant.
You only schedule appointments; never diagnose, prescribe, or give medical advice.
Identify callers only by the phone number they speak. Never use caller ID, login or OTP.
Before every booking or cancellation: ask for the phone number, read it back digit by digit,
ask if it is correct, wait for a clear spoken yes, then call confirm_phone_number.
Never call a mutation tool unless confirm_phone_number returned confirmed=true.
For booking, ask for specialty and date, check availability, offer returned slots, and confirm
the selected doctor/date/time before booking. Never claim success unless the tool returns success.
All times are Asia/Kolkata. Speak naturally and concisely."""

def digits(value): return re.sub(r"\D", "", value or "")

async def run_bot(connection):
    confirmed = {"phone": None}
    transport = SmallWebRTCTransport(webrtc_connection=connection,
        params=SmallWebRTCParams(audio_in_enabled=True, audio_out_enabled=True))
    stt = ElevenLabsSTTService(api_key=os.environ["ELEVENLABS_API_KEY"])
    llm = GoogleLLMService(api_key=os.environ["GEMINI_API_KEY"],
        model=os.getenv("GEMINI_MODEL","gemini-2.0-flash"), system_instruction=SYSTEM_PROMPT)
    tts = ElevenLabsTTSService(api_key=os.environ["ELEVENLABS_API_KEY"],
        voice_id=os.environ["ELEVENLABS_VOICE_ID"])

    async def check_doctor_availability(params: FunctionCallParams, specialty: str, appointment_date: str = ""):
        """Find available slots for a specialty and optional date.
        Args:
            specialty: Specialty such as Cardiology or Dermatology.
            appointment_date: Optional date formatted YYYY-MM-DD.
        """
        try:
            on_date = date.fromisoformat(appointment_date) if appointment_date else None
            async with SessionLocal() as db:
                result = await services.availability(db, specialty=specialty, on_date=on_date)
            await params.result_callback({"available_slots": result[:20]})
        except Exception as exc: await params.result_callback({"error": str(exc)})

    async def confirm_phone_number(params: FunctionCallParams, phone: str, caller_confirmed: bool):
        """Store phone number after caller confirms the digit-by-digit read-back.
        Args:
            phone: Phone number spoken by the caller.
            caller_confirmed: True only after an explicit spoken yes.
        """
        try:
            normalized = services.normalize_phone(phone)
            confirmed["phone"] = normalized if caller_confirmed else None
            await params.result_callback({"confirmed": bool(caller_confirmed),
                "message": "Phone number confirmed." if caller_confirmed else "Ask caller to repeat the number."})
        except ValueError as exc:
            confirmed["phone"] = None
            await params.result_callback({"confirmed": False, "error": str(exc)})

    async def book_appointment(params: FunctionCallParams, doctor_id: int, slot_id: int, phone: str):
        """Book an available slot. Requires phone confirmation earlier in this call.
        Args:
            doctor_id: Doctor ID from availability result.
            slot_id: Slot ID selected by caller.
            phone: Caller phone number confirmed in this call.
        """
        try:
            normalized = services.normalize_phone(phone)
            if not confirmed["phone"] or digits(normalized) != digits(confirmed["phone"]):
                await params.result_callback({"success": False, "error": "Phone number not confirmed in this call."}); return
            async with SessionLocal() as db: result = await services.book(db, doctor_id, slot_id, normalized)
            confirmed["phone"] = None
            await params.result_callback({"success": True, "appointment": result})
        except Exception as exc: await params.result_callback({"success": False, "error": str(exc)})

    async def cancel_appointment(params: FunctionCallParams, phone: str, appointment_id: int = 0):
        """Cancel an active appointment after phone confirmation.
        Args:
            phone: Caller phone number confirmed in this call.
            appointment_id: Optional appointment ID; zero cancels most recent active booking.
        """
        try:
            normalized = services.normalize_phone(phone)
            if not confirmed["phone"] or digits(normalized) != digits(confirmed["phone"]):
                await params.result_callback({"success": False, "error": "Phone number not confirmed in this call."}); return
            async with SessionLocal() as db: result = await services.cancel(db, normalized, appointment_id or None)
            confirmed["phone"] = None
            await params.result_callback({"success": True, "appointment": result})
        except Exception as exc: await params.result_callback({"success": False, "error": str(exc)})

    context = LLMContext(messages=[{"role":"system","content":SYSTEM_PROMPT}],
        tools=[check_doctor_availability, confirm_phone_number, book_appointment, cancel_appointment])
    aggregator = LLMContextAggregatorPair(context)
    pipeline = Pipeline([transport.input(), stt, aggregator.user(), llm, tts,
        transport.output(), aggregator.assistant()])
    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))
    await PipelineRunner().run(task)
