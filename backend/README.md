# StepWise API

The FastAPI service provides registration and login, conversation history and branches, SSE chat streaming, password reset, and faculty syllabus mappings.

## Project diagrams

The current system context, DFDs, ERD, UML use-case, class, and chat-sequence diagrams are in [`docs/project-diagrams.md`](docs/project-diagrams.md). The document distinguishes features present in the code from future scope.

## Setup

Create a Python virtual environment, install `requirements.txt`, and copy `.env.example` to `.env`. Replace `STEPWISE_SECRET_KEY` with a random value before using real accounts. `main.py` loads `.env` at startup. See the frontend README for the complete local setup and Ollama instructions.

Start the service from this directory:

```powershell
.\.venv\Scripts\uvicorn.exe main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API docs: <http://127.0.0.1:8000/docs>.

Run automated checks with `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` followed by `.\.venv\Scripts\python.exe -m pytest -q`.

## Local model

The default model is `gemma4:e2b`. Set `STEPWISE_OLLAMA_MODEL` to a different Ollama model. Ollama must be running before a student submits a question. A model failure is recorded as a readable assistant message so the conversation can be retried.

## Configuration and safety

- `STEPWISE_ENV=production` requires a random `STEPWISE_SECRET_KEY` with at least 32 characters.
- Faculty registration requires `STEPWISE_FACULTY_INVITE_CODE`; do not commit the value.
- Set SMTP variables to enable remote password-reset emails. Without SMTP, reset links are only returned for loopback requests.
- Keep `STEPWISE_CORS_ORIGINS` restricted to the frontend origins you use.
- SQLite is suitable for local use and demonstration; back up the database file before replacing or migrating it.
