# StepWise: An Interactive Local Socratic Tutoring System

StepWise is an offline-first, privacy-preserving Socratic tutoring platform built with **React (Vite)**, **FastAPI**, **SQLite / SQLAlchemy**, and **Ollama** running local open-weights models (such as Gemma). Instead of giving direct answers or spoon-feeding code, StepWise guides students step-by-step using probing questions, subject personas, cognitive frustration tracking, misconception logging, and moderated peer debugging rooms.

## Key Features

- **Socratic Guidance & Token Streaming:** Streams step-by-step hints over Server-Sent Events (SSE) with KaTeX math rendering and syntax-highlighted code blocks, backed by conversation tree branching (`parent_message_id`) and JWT authentication.
- **Affective-Socratic Frustration Loop:** Tracks conversational stagnation and repeated loops to dynamically adjust hinting strategies without leaking direct solutions.
- **Automated Misconception Graph:** Classifies recurring logical and syntax errors into SQLite misconception records surfaced through a Learning Insights view.
- **Peer Blindspot Sandbox Sync:** Real-time WebSocket rooms for anonymous peer debugging moderated by the local LLM.
- **Faculty Syllabus Mappings:** Allows faculty to define subject, module, chapter, and persona context.

## Tech Stack

- **Frontend:** React, Vite, Tailwind CSS, KaTeX
- **Backend:** Python 3.10+, FastAPI, Uvicorn, SQLAlchemy, WebSockets
- **Database:** SQLite
- **Local AI Runtime:** Ollama (quantized Gemma weights)

## Running Locally

### 1. Start Ollama & Pull a Model
Ensure Ollama is running locally (`http://localhost:11434`) and pull your configured model:
```bash
ollama pull gemma2:2b