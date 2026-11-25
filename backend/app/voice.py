import os
import re
from datetime import date

import aiohttp

from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMFullResponseEndFrame, LLMTextFrame, TranscriptionFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.services.elevenlabs.stt import ElevenLabsSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from .db import SessionLocal
from . import services


SYSTEM_PROMPT = """You are VoiceCare, a friendly doctor appointment booking assistant.
You only help users check availability, book appointments, and cancel appointments.
Never diagnose, prescribe, or give medical advice.

Identify callers only by the phone number they speak. Never use caller ID, login, or OTP.
Before booking or cancellation:
1. Ask the caller to speak their phone number.
2. Repeat the complete number back digit by digit.
3. Ask whether the number is correct.
4. Wait for a clear spoken yes.
5. Only then call confirm_phone_number with caller_confirmed=true.
If the caller says no, correct the number and repeat the confirmation process.
Never call book_appointment or cancel_appointment unless the confirmation tool has
returned confirmed=true during this same call.

For booking, ask for the specialty and preferred date, check availability, offer
only returned slots, and confirm the selected doctor/date/time with the caller
before booking. Do not invent doctors or slots. Never claim success unless the
booking/cancellation tool returns success. All appointment dates and times are
in Asia/Kolkata. Speak naturally and concisely."""


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


class TranscriptRecorder(FrameProcessor):
    """Send finalized pipeline transcripts to the dashboard's call event stream."""

    def __init__(self, call_id, who, event_sink):
        super().__init__()
        self._call_id = call_id
        self._who = who
        self._event_sink = event_sink
        self._assistant_text = []

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            text = None
            if self._who == "you" and isinstance(frame, TranscriptionFrame):
                text = frame.text.strip()
            elif self._who == "assistant":
                if isinstance(frame, LLMTextFrame):
                    self._assistant_text.append(frame.text)
                elif isinstance(frame, LLMFullResponseEndFrame):
                    text = "".join(self._assistant_text).strip()
                    self._assistant_text.clear()

            if text and self._call_id and self._event_sink:
                self._event_sink(
                    self._call_id,
                    {"type": "transcript", "who": self._who, "text": text},
                )
        await self.push_frame(frame, direction)


async def run_bot(connection, call_id=None, event_sink=None):
    """Run one Pipecat voice session for a browser WebRTC connection."""
    confirmed = {"phone": None}
    http_session = aiohttp.ClientSession()

    try:
        transport = SmallWebRTCTransport(
            webrtc_connection=connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
            ),
        )

        vad = VADProcessor(vad_analyzer=SileroVADAnalyzer())
        stt = ElevenLabsSTTService(
            api_key=os.environ["ELEVENLABS_API_KEY"],
            aiohttp_session=http_session,
        )

        llm = GoogleLLMService(
            api_key=os.environ["GEMINI_API_KEY"],
            model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            system_instruction=SYSTEM_PROMPT,
        )

        tts = ElevenLabsTTSService(
            api_key=os.environ["ELEVENLABS_API_KEY"],
            voice_id=os.environ["ELEVENLABS_VOICE_ID"],
        )

        async def check_doctor_availability(params: FunctionCallParams):
            args = params.arguments
            specialty = str(args.get("specialty", "")).strip()
            appointment_date = str(args.get("appointment_date", "")).strip()
            doctor_id = args.get("doctor_id")

            try:
                if not specialty and not doctor_id:
                    await params.result_callback(
                        {"success": False, "error": "Provide a specialty or doctor ID."}
                    )
                    return

                on_date = date.fromisoformat(appointment_date) if appointment_date else None
                async with SessionLocal() as db:
                    result = await services.availability(
                        db,
                        doctor_id=int(doctor_id) if doctor_id is not None else None,
                        specialty=specialty or None,
                        on_date=on_date,
                    )

                await params.result_callback(
                    {"success": True, "available_slots": result[:20]}
                )
            except Exception as exc:
                await params.result_callback({"success": False, "error": str(exc)})

        async def confirm_phone_number(params: FunctionCallParams):
            args = params.arguments
            phone = str(args.get("phone", "")).strip()
            caller_confirmed = args.get("caller_confirmed") is True

            try:
                if not caller_confirmed:
                    confirmed["phone"] = None
                    await params.result_callback(
                        {
                            "confirmed": False,
                            "message": "Do not book or cancel. Ask the caller to repeat the number.",
                        }
                    )
                    return

                normalized = services.normalize_phone(phone)
                if len(_digits(normalized)) < 10:
                    raise ValueError("Please collect a valid phone number.")

                confirmed["phone"] = normalized
                await params.result_callback(
                    {
                        "confirmed": True,
                        "message": "Phone number confirmed for this call.",
                    }
                )
            except Exception as exc:
                confirmed["phone"] = None
                await params.result_callback(
                    {"confirmed": False, "error": str(exc)}
                )

        async def book_appointment(params: FunctionCallParams):
            args = params.arguments
            doctor_id = args.get("doctor_id")
            slot_id = args.get("slot_id")
            phone = confirmed["phone"]

            if not phone:
                await params.result_callback(
                    {
                        "success": False,
                        "error": "Phone number has not been confirmed in this call.",
                    }
                )
                return

            try:
                async with SessionLocal() as db:
                    result = await services.book(
                        db,
                        int(doctor_id),
                        int(slot_id),
                        phone,
                    )
                confirmed["phone"] = None
                await params.result_callback(
                    {"success": True, "appointment": result}
                )
            except Exception as exc:
                await params.result_callback(
                    {"success": False, "error": str(exc)}
                )

        async def cancel_appointment(params: FunctionCallParams):
            args = params.arguments
            appointment_id = args.get("appointment_id")
            phone = confirmed["phone"]

            if not phone:
                await params.result_callback(
                    {
                        "success": False,
                        "error": "Phone number has not been confirmed in this call.",
                    }
                )
                return

            try:
                async with SessionLocal() as db:
                    result = await services.cancel(
                        db,
                        phone,
                        int(appointment_id) if appointment_id else None,
                    )
                confirmed["phone"] = None
                await params.result_callback(
                    {"success": True, "appointment": result}
                )
            except Exception as exc:
                await params.result_callback(
                    {"success": False, "error": str(exc)}
                )

        tools = [
            FunctionSchema(
                name="check_doctor_availability",
                description="Find available appointment slots for a specialty or doctor, optionally on a specific date.",
                properties={
                    "specialty": {
                        "type": "string",
                        "description": "Doctor specialty, for example Cardiology or Dermatology.",
                    },
                    "doctor_id": {
                        "type": "integer",
                        "description": "Optional doctor ID from the doctors list.",
                    },
                    "appointment_date": {
                        "type": "string",
                        "description": "Optional date in YYYY-MM-DD format.",
                    },
                },
                required=[],
                handler=check_doctor_availability,
            ),
            FunctionSchema(
                name="confirm_phone_number",
                description="Record the caller's phone number only after repeating it digit by digit and receiving a clear spoken yes.",
                properties={
                    "phone": {
                        "type": "string",
                        "description": "The phone number spoken by the caller.",
                    },
                    "caller_confirmed": {
                        "type": "boolean",
                        "description": "True only after the caller clearly confirms the read-back.",
                    },
                },
                required=["phone", "caller_confirmed"],
                handler=confirm_phone_number,
            ),
            FunctionSchema(
                name="book_appointment",
                description="Book the caller's selected available slot. Only call after phone confirmation and after the caller confirms the doctor and time.",
                properties={
                    "doctor_id": {
                        "type": "integer",
                        "description": "Doctor ID returned by the availability tool.",
                    },
                    "slot_id": {
                        "type": "integer",
                        "description": "Slot ID returned by the availability tool.",
                    },
                },
                required=["doctor_id", "slot_id"],
                handler=book_appointment,
            ),
            FunctionSchema(
                name="cancel_appointment",
                description="Cancel the caller's active appointment after phone confirmation. If appointment_id is omitted, cancel the most recent active appointment for the confirmed phone number.",
                properties={
                    "appointment_id": {
                        "type": "integer",
                        "description": "Optional appointment ID to cancel.",
                    },
                },
                required=[],
                handler=cancel_appointment,
            ),
        ]

        context = LLMContext(tools=tools)
        context_aggregator = LLMContextAggregatorPair(context)

        pipeline = Pipeline(
            [
                transport.input(),
                vad,
                stt,
                TranscriptRecorder(call_id, "you", event_sink),
                context_aggregator.user(),
                llm,
                TranscriptRecorder(call_id, "assistant", event_sink),
                tts,
                transport.output(),
                context_aggregator.assistant(),
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(allow_interruptions=True),
        )
        await PipelineRunner().run(task)

    finally:
        await http_session.close()
