# VoiceCare — Voice AI Doctor Appointment Assistant

A full stack SDE Intern Round 1 assignment project for checking doctor availability and managing appointments through a voice conversation. The React dashboard also exposes doctor, slot, appointment, and live call transcript information.

## Current status

- The React dashboard and REST APIs are running locally.
- The browser connects to the backend using Pipecat SmallWebRTC; the browser microphone is sent to the backend voice pipeline.
- The latest recorded call log showed ElevenLabs STT transcribing speech, Gemini invoking `cancel_appointment`, and the appointment being marked cancelled. The assistant then hit Gemini HTTP 429 because the Gemini free tier's daily request quota for the configured model had been used up. This is a provider quota limit, not an audio or transcript transport failure. Further model replies require quota to reset or a Gemini project/model with available quota.
- Live voice requires valid provider credentials in the backend environment. Never commit `.env` files or paste keys into logs/issues.

## Features

- Doctor list and specialties, with upcoming appointment slots.
- Check availability, book an appointment, and cancel an appointment through the voice agent.
- The voice flow asks the caller to say a phone number, reads it back, and requires explicit confirmation before booking or cancellation. Confirmation is held for the current call and is not a login or cryptographic identity check.
- Live conversation transcript events are streamed to the React dashboard using Server-Sent Events (SSE).
- Recent appointment data refreshes after booking or cancellation.
- SQLite persistence and demo doctors/slots initialized by the backend.
- Dashboard also includes direct demo booking/cancellation controls for testing the REST workflow.

## Architecture and voice flow

```text
Browser microphone
  -> Pipecat SmallWebRTC transport / FastAPI signaling
  -> VAD and ElevenLabs speech-to-text
  -> Gemini LLM with appointment tools
  -> FastAPI/SQLite appointment services
  -> ElevenLabs text-to-speech
  -> Browser audio playback

Transcription and assistant text frames -> FastAPI SSE -> React live transcript
```

The voice agent exposes `check_doctor_availability`, `confirm_phone_number`, `book_appointment`, and `cancel_appointment`. Appointment changes use the existing backend service and database. The confirmation tool records the caller's affirmative response for the current call; booking/cancellation handlers reject a missing or mismatched confirmation.

## Requirements

- Python 3.11 or newer
- Node.js and npm (use a supported current LTS release)
- Google Gemini API key
- ElevenLabs API key and voice ID
- A modern browser with microphone access (localhost is suitable for local development)

## Run locally (Windows PowerShell)

Open two terminals from the repository root.

### 1. Configure and run the backend

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and set `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, and `ELEVENLABS_VOICE_ID`. Keep this file private; it is ignored by Git. Then run:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

The API is at `http://localhost:8000`; interactive API docs are at `http://localhost:8000/docs`.

### 2. Configure and run the frontend

In a second terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev -- --port 5173
```

Open `http://localhost:5173` and allow microphone access when prompted.

### Use backend port 8001

If port 8000 is occupied or you run the backend on 8001, start it with:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8001
```

Set `VITE_API_URL=http://localhost:8001` in `frontend/.env`, then restart the Vite server. The frontend `.env.example` intentionally uses the default backend port 8000.

### Linux / WSL equivalent

Run these in separate terminals from the repository root:

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
# Edit backend/.env and set the three provider values
python -m uvicorn app.main:app --reload --port 8001
```

```bash
cd frontend
cp .env.example .env
# If backend is on 8001, set VITE_API_URL=http://localhost:8001 in frontend/.env
npm ci
npm run dev -- --port 5173
```

## Environment variables

Backend variables are listed in `backend/.env.example`:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy database URL; default is local SQLite at `backend/voicecare.db`. |
| `FRONTEND_ORIGIN` | Allowed browser origin for local CORS; default is `http://localhost:5173`. |
| `GEMINI_API_KEY` | Private Gemini API credential. |
| `GEMINI_MODEL` | Gemini model name; example template currently uses `gemini-3.6-flash`. Provider model availability and quota depend on the Google project. |
| `ELEVENLABS_API_KEY` | Private ElevenLabs credential used by STT and TTS. |
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice used for speech output. |

Frontend variable `VITE_API_URL` is the backend base URL. Frontend variables are bundled into browser code, so **never put provider secrets or private keys in `frontend/.env` or any `VITE_*` variable**. Provider credentials belong only in `backend/.env`.

## API routes

- `GET /api/health` — backend health check.
- `GET /api/doctors` — doctor directory.
- `GET /api/slots` — upcoming slots (optional `doctor_id` and `date=YYYY-MM-DD` query parameters).
- `GET /api/appointments` — appointments.
- `POST /api/appointments/book` — direct/demo booking endpoint.
- `POST /api/appointments/cancel` — direct/demo cancellation endpoint.
- `POST /api/calls` — create a call/transcript event session.
- `GET /api/calls/{call_id}/events` — SSE transcript/event stream.
- `POST /api/offer` and `PATCH /api/offer` — Pipecat SmallWebRTC signaling and ICE updates.

## Verify and demo

1. Check `http://localhost:8000/api/health` (or port 8001 if configured) and `http://localhost:8000/docs`.
2. Start the frontend, grant microphone permission, and start a call.
3. Say a request to check availability. Confirm the spoken words appear in Live Transcript and the assistant response is audible.
4. For a booking or cancellation, state the phone number when asked, listen to the read-back, and clearly confirm it. Check the updated appointment in the dashboard.
5. Check backend logs for provider errors. A Gemini `429 RESOURCE_EXHAUSTED` means the configured project's quota is exhausted; check Google AI Studio quota/billing or wait for reset before continuing the voice demo. A successful booking/cancellation may already have completed before a later LLM request returns 429, so verify appointment state before retrying a mutation.

Known observed log: a cancellation for the spoken and confirmed phone number completed and returned an appointment status of `cancelled`; the next Gemini generation failed with a free-tier daily request limit error for `gemini-3.6-flash` (HTTP 429). This is an observed run, not a guarantee of provider availability.

## Tests and build

Run the backend phone normalization/confirmation tests from `backend`:

```powershell
python -m pytest tests/test_phone.py -q
```

Build the frontend from `frontend`:

```powershell
npm ci
npm run build
```

These are commands for a fresh clone. Live voice behavior additionally depends on valid credentials, network access, provider quota, browser microphone permission, and compatible Pipecat/provider APIs.

## GitHub and secret safety

- Commit `backend/.env.example` and `frontend/.env.example`, never the actual `.env` files.
- The root `.gitignore` excludes environment files, virtual environments, dependencies/build output, caches, logs, and SQLite database files.
- The local `backend/voicecare.db` may contain test appointments and phone numbers; do not upload it.
- Review `git status` and staged file names before pushing. If a secret was ever committed, deleting it in a later commit is insufficient: revoke/rotate the key and remove it from repository history.

## Assignment submission checklist

- Push the source and README to the assigned GitHub repository.
- Confirm a clean clone can follow the setup instructions.
- Record a short demo (assignment limit: 3 minutes) showing availability lookup, spoken phone-number read-back and explicit confirmation, booking, cancellation, transcript, and dashboard updates. Avoid showing API keys or real personal data.
- Be prepared to explain the microphone-to-STT-to-LLM/tools-to-TTS flow and how the confirmation gate works.

## Scope and limitations

This is an internship assignment/demo, not a production medical system. It does not provide medical advice or establish verified identity; the spoken phone-number confirmation is a workflow safeguard only. A production deployment would need authentication and authorization, audit logging, rate limiting, encryption, consent and retention controls, robust phone normalization, timezone policies, monitoring, and a managed database.
