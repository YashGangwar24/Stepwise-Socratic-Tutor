# StepWise

**StepWise: An Interactive Local Socratic Tutoring System Powered by Large Language Models**

StepWise is a local-first tutoring prototype. A student asks a question and a locally running Ollama model guides them with short questions rather than immediately giving a complete solution. FastAPI stores conversations in SQLite; the React interface displays responses as they stream.

## Phase 1 scope

- Stream tutor responses to the chat using Server-Sent Events.
- Edit a previous student message to create a separate conversation branch while keeping the original path.
- Render Markdown and math, highlight code blocks, and copy code.
- Offer subject-specific chats for Algorithms, LAW, Biology, DBMS, and Mathematics. Clear cross-subject questions are redirected to the matching subject.

The chat also has browser speech-to-text and text/code/PDF attachments. Speech recognition depends on browser support and microphone permission; audio handling is controlled by the browser and is not guaranteed to stay on-device. Attachments are read in the browser and included in the prompt; images and other binary files are not interpreted. PDFs must contain selectable text; scanned/image-only PDFs are not supported.

## Architecture

```text
React + Vite
  | JSON requests and POST-based SSE streaming
FastAPI + Pydantic
  | SQLAlchemy
SQLite
  |
Ollama Python client -> local Ollama model
```

The backend owns conversation history and branch selection. Message records use `parent_message_id` to form a message tree. Tutor inference uses Ollama and the configured local model; it does not call a hosted LLM API.

## Requirements

- Python 3.10 or newer
- Node.js 20.19+ or 22.12+
- Ollama installed and running locally
- The model configured by `STEPWISE_OLLAMA_MODEL` (defaults to `gemma4:e2b`)

## Run on Windows PowerShell

From the `stepwise` project folder:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env`: generate a unique key with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and set it as `STEPWISE_SECRET_KEY`. Keep `.env` private. The example file is only a template.

Make sure Ollama is running and the model is available:

```powershell
ollama pull gemma4:e2b
```

If Ollama is not already running as a service, start it in a separate window with `ollama serve`.

In the backend window:

```powershell
.\.venv\Scripts\uvicorn.exe main:app --reload --host 127.0.0.1 --port 8000
```

In a second PowerShell window:

```powershell
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173>. The API documentation is at <http://127.0.0.1:8000/docs>.

If the API runs at another address, create `frontend/.env.local` with `VITE_API_BASE_URL=http://127.0.0.1:8000`, then restart Vite.

## Faculty accounts

New accounts are students by default. Faculty registration requires the administrator's `STEPWISE_FACULTY_INVITE_CODE`, configured in the backend environment. Do not publish that code with the project. Without it, use a student account or provision a faculty account through a trusted administrative process.

## Checks

Backend tests (from `backend`):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The live model compliance test is opt-in; it runs only when `STEPWISE_RUN_LIVE_EVAL=1` and Ollama is available.

Frontend checks (from `frontend`):

```powershell
npm run lint
npm run build
```

## Important configuration

See `backend/.env.example` for the database, JWT, CORS, frontend URL, SMTP, and model settings. For a deployed environment set `STEPWISE_ENV=production`, provide a private `STEPWISE_SECRET_KEY`, configure SMTP for password resets, and restrict CORS origins to the deployed frontend. The default SQLite database is local development storage, not a managed backup or multi-user production database.

## Known limits

- Socratic behavior depends on the selected local model and prompt; it is not guaranteed to be correct for every request.
- Cross-subject protection uses a conservative topic-keyword check plus subject-focused model instructions; vague or unusual wording may not always be classified correctly.
- Streaming and the non-streaming API use local inference; inference quality and speed depend on hardware and the installed model.
- Local password-reset links are returned only to loopback requests when SMTP is not configured. Remote password resets require SMTP.
- Voice input is browser speech recognition, not the planned local Whisper.cpp integration. Audio handling depends on the browser and may use a browser provider.
- Attachments support up to five files and 7,000 extracted characters combined. Text/code files are limited to 10 KB each; PDFs are limited to 5 MB and 20 pages, and must contain selectable text. Their extracted contents are embedded in and saved with the chat message; there is no separate file upload store. Messages are limited to 10,000 characters.

## Project context

Prepared by Yash Gangwar (24UCOMP058), Central University of Karnataka, with guidance from Dr. Madhuri Kagale R. Research extensions such as local RAG, sandboxed code execution, Whisper.cpp, vision, peer rooms, and faculty analytics are outside Phase 1.
