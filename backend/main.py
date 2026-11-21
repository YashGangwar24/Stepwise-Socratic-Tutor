import asyncio
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import time
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, List
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from ai_engine import MISCONCEPTION_TAXONOMY, classify_misconception, facilitate_peer_debugging, generate_socratic_response, generate_socratic_response_stream
from database import SessionLocal, create_tables, get_db
from learning_support import estimate_support_level
from subject_scope import mismatched_subject
from models import Conversation, Message, MisconceptionLog, SyllabusMapping, User

APP_ENV = os.getenv("STEPWISE_ENV", "development").strip().lower()
SECRET_KEY = os.getenv("STEPWISE_SECRET_KEY", "stepwise-dev-secret-key-change-me")
if APP_ENV == "production" and (
    SECRET_KEY in {"stepwise-dev-secret-key-change-me", "replace-with-a-unique-random-secret"}
    or len(SECRET_KEY) < 32
):
    raise RuntimeError("Set STEPWISE_SECRET_KEY to a random secret of at least 32 characters before production startup")
ALGORITHM = os.getenv("STEPWISE_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("STEPWISE_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
MAX_CHAT_CHARS = 10_000
MAX_PEER_MESSAGE_CHARS = 2_000
MAX_PEER_CODE_CHARS = 8_000
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "STEPWISE_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app = FastAPI(title="StepWise API")
create_tables()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_CHAT_CHARS)
    subject: str = Field(min_length=1, max_length=100)
    conversation_id: int | None = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    parent_message_id: int | None = None


class MessageEditRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_CHAT_CHARS)
    regenerate: bool = False


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New Conversation", max_length=120)
    subject: str = Field(default="Uncategorized", min_length=1, max_length=100)


class PeerRoomRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=100)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Choose a subject")
        return normalized


VALID_USER_ROLES = {"student", "faculty", "instructor"}


class UserRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)
    role: str = Field(default="student", max_length=20)
    faculty_invite_code: str | None = Field(default=None, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid email address")
        return normalized


class UserLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class SyllabusMappingRequest(BaseModel):
    subject: str
    module: str
    chapter: str
    persona: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None = None
    role: str = "student"
    is_active: bool = True


def normalize_user_role(role: str | None) -> str:
    if role is None:
        return "student"
    normalized = role.strip().lower()
    if normalized in {"faculty", "instructor"}:
        return "faculty"
    if normalized not in VALID_USER_ROLES:
        raise ValueError(f"Unsupported role '{role}'. Allowed roles: {sorted(VALID_USER_ROLES)}")
    return normalized


def conversation_title_from_message(message: str) -> str:
    title = " ".join(message.split())
    if len(title) > 60:
        shortened = title[:57].rsplit(" ", 1)[0]
        title = f"{shortened or title[:57]}..."
    return title


def get_message_path(db: Session, conversation_id: int, parent_message_id: int | None) -> list[Message]:
    """Return the selected root-to-leaf history path for a message branch."""
    if parent_message_id is None:
        return []
    current = db.query(Message).filter(
        Message.id == parent_message_id,
        Message.conversation_id == conversation_id,
    ).first()
    if current is None:
        raise HTTPException(status_code=404, detail="Message not found in this conversation")
    path = []
    while current is not None:
        path.append(current)
        current = current.parent_message
    return list(reversed(path))


def require_faculty_role(current_user: User):
    if current_user.role != "faculty":
        raise HTTPException(status_code=403, detail="Faculty access required")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def password_reset_version(user: User) -> str:
    return hmac.new(
        SECRET_KEY.encode(), user.hashed_password.encode(), "sha256"
    ).hexdigest()


def create_password_reset_token(user: User) -> str:
    return create_access_token(
        {
            "sub": user.email,
            "purpose": "password_reset",
            "password_version": password_reset_version(user),
        },
        expires_delta=timedelta(minutes=15),
    )


def password_reset_email_configured() -> bool:
    username = os.getenv("STEPWISE_SMTP_USERNAME")
    password = os.getenv("STEPWISE_SMTP_PASSWORD")
    return bool(
        os.getenv("STEPWISE_SMTP_HOST")
        and os.getenv("STEPWISE_SMTP_FROM")
        and bool(username) == bool(password)
    )


def is_loopback_request(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def send_password_reset_email(recipient: str, reset_url: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Reset your StepWise password"
    message["From"] = os.environ["STEPWISE_SMTP_FROM"]
    message["To"] = recipient
    message.set_content(
        "Use this link within 15 minutes to reset your StepWise password:\n\n"
        f"{reset_url}\n\nIf you did not request this, you can ignore this email."
    )

    with smtplib.SMTP(
        os.environ["STEPWISE_SMTP_HOST"],
        int(os.getenv("STEPWISE_SMTP_PORT", "587")),
        timeout=10,
    ) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        username = os.getenv("STEPWISE_SMTP_USERNAME")
        password = os.getenv("STEPWISE_SMTP_PASSWORD")
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if email is None or payload.get("purpose") == "password_reset":
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.query(User).filter(User.email == email).first()
    if (
        user is None
        or not user.is_active
        or payload.get("password_version") != password_reset_version(user)
    ):
        raise credentials_exception
    return user


def authenticate_websocket_token(token: str, db: Session) -> User | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email or payload.get("purpose") == "password_reset":
            return None
        user = db.query(User).filter(User.email == email).first()
        if user and user.is_active and payload.get("password_version") == password_reset_version(user):
            return user
    except JWTError:
        pass
    return None


def log_misconception(db: Session, user_id: int, conversation_id: int, message_id: int, message: str, reply: str):
    try:
        result = classify_misconception(message, reply)
        if result:
            code, confidence = result
            db.add(MisconceptionLog(user_id=user_id, conversation_id=conversation_id,
                                    source_message_id=message_id, category_code=code, confidence=confidence))
            db.commit()
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("Misconception logging failed")


async def classify_and_store_misconception(user_id: int, conversation_id: int, message_id: int,
                                          message: str, reply: str):
    """Run the optional second local inference without holding the chat stream open."""
    result = await asyncio.to_thread(classify_misconception, message, reply)
    if not result:
        return
    db = SessionLocal()
    try:
        db.add(MisconceptionLog(user_id=user_id, conversation_id=conversation_id, source_message_id=message_id,
                                category_code=result[0], confidence=result[1]))
        db.commit()
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("Could not persist misconception observation")
    finally:
        db.close()


peer_rooms: dict[str, dict] = {}
PEER_ROOM_TTL = 60 * 60


def prune_peer_rooms():
    cutoff = time.time() - PEER_ROOM_TTL
    for code in [code for code, room in peer_rooms.items() if room["created"] < cutoff and not room["sockets"]]:
        peer_rooms.pop(code, None)


async def expire_peer_room(code: str, created_at: float):
    await asyncio.sleep(PEER_ROOM_TTL)
    room = peer_rooms.get(code)
    if room and room["created"] == created_at:
        await peer_broadcast(room, {"type": "closed"})
        peer_rooms.pop(code, None)
        for socket in list(room["sockets"].values()):
            try:
                await socket.close(code=1000)
            except Exception:
                pass


async def peer_broadcast(room: dict, payload: dict):
    stale = []
    for socket in list(room["sockets"].values()):
        try:
            await socket.send_json(payload)
        except Exception:
            stale.append(socket)
    for socket in stale:
        for user_id, candidate in list(room["sockets"].items()):
            if candidate is socket:
                room["sockets"].pop(user_id, None)


@app.get("/")
def read_root():
    return {"status": "StepWise Backend is running!"}


@app.get("/api/syllabus/mappings")
def list_syllabus_mappings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_faculty_role(current_user)
    mappings = (
        db.query(SyllabusMapping)
        .filter(SyllabusMapping.user_id == current_user.id)
        .order_by(SyllabusMapping.created_at.desc())
        .all()
    )
    return [
        {
            "id": mapping.id,
            "user_id": mapping.user_id,
            "subject": mapping.subject,
            "module": mapping.module,
            "chapter": mapping.chapter,
            "persona": mapping.persona,
            "created_at": mapping.created_at,
        }
        for mapping in mappings
    ]


@app.post("/api/syllabus/mappings")
def create_syllabus_mapping(
    data: SyllabusMappingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_faculty_role(current_user)
    mapping = SyllabusMapping(
        user_id=current_user.id,
        subject=data.subject,
        module=data.module,
        chapter=data.chapter,
        persona=data.persona,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return {
        "id": mapping.id,
        "user_id": mapping.user_id,
        "subject": mapping.subject,
        "module": mapping.module,
        "chapter": mapping.chapter,
        "persona": mapping.persona,
        "created_at": mapping.created_at,
    }


@app.post("/api/conversations")
def create_conversation(
    data: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = Conversation(
        user_id=current_user.id,
        title=data.title or "New Conversation",
        subject=data.subject,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {
        "id": conversation.id,
        "user_id": conversation.user_id,
        "title": conversation.title,
        "subject": conversation.subject,
        "support_level": conversation.frustration_score,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


@app.get("/api/learning-insights")
def learning_insights(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(MisconceptionLog.category_code, MisconceptionLog.confidence,
                     MisconceptionLog.created_at, MisconceptionLog.is_sample)
            .filter(MisconceptionLog.user_id == current_user.id)
            .order_by(MisconceptionLog.created_at.desc()).limit(500).all())
    grouped = {}
    for code, confidence, created_at, is_sample in rows:
        key = (code, is_sample)
        item = grouped.setdefault(key, {"code": code, "label": MISCONCEPTION_TAXONOMY.get(code, code),
                                        "is_sample": is_sample, "count": 0,
                                        "confidence_total": 0.0, "last_seen": created_at})
        item["count"] += 1
        item["confidence_total"] += confidence
    categories = [{**item, "average_confidence": round(item.pop("confidence_total") / item["count"], 2)}
                  for item in grouped.values()]
    return {"total_observations": len(rows), "categories": sorted(categories, key=lambda item: (-item["count"], item["label"], item["is_sample"]))}


@app.post("/api/peer-rooms")
async def create_peer_room(data: PeerRoomRequest, current_user: User = Depends(get_current_user)):
    prune_peer_rooms()
    if len(peer_rooms) >= 100:
        raise HTTPException(status_code=503, detail="Peer rooms are busy. Try again shortly.")
    code = secrets.token_urlsafe(9)
    peer_rooms[code] = {"owner": current_user.id, "subject": data.subject.strip(), "created": time.time(),
                        "sockets": {}, "aliases": {}, "messages": [], "code": ""}
    asyncio.create_task(expire_peer_room(code, peer_rooms[code]["created"]))
    return {"code": code, "subject": data.subject.strip(), "expires_in_seconds": PEER_ROOM_TTL}


@app.post("/api/peer-rooms/demo-moderator")
async def peer_demo_moderator(current_user: User = Depends(get_current_user)):
    """Generate an ephemeral, real local-LLM facilitator message for the sample preview."""
    sample_messages = [
        {"alias": "Learner A", "content": "I used the list length as the final index."},
        {"alias": "Learner B", "content": "I think range stops before its end. Let's trace three items."},
    ]
    sample_code = "for i in range(len(values) + 1):\n    print(values[i])"
    try:
        content = await asyncio.to_thread(facilitate_peer_debugging, "Algorithms", sample_messages, sample_code)
        return {"alias": "StepWise moderator", "content": content, "is_sample": True}
    except Exception as exc:
        logging.getLogger(__name__).warning("Sample peer moderator is unavailable", exc_info=True)
        raise HTTPException(status_code=503, detail="The local model could not generate a sample moderator message.") from exc


@app.delete("/api/peer-rooms/{code}")
async def close_peer_room(code: str, current_user: User = Depends(get_current_user)):
    room = peer_rooms.get(code)
    if room is None or room["owner"] != current_user.id:
        raise HTTPException(status_code=404, detail="Peer room not found")
    await peer_broadcast(room, {"type": "closed"})
    peer_rooms.pop(code, None)
    for socket in list(room["sockets"].values()):
        try:
            await socket.close(code=1000)
        except Exception:
            pass
    return {"closed": True}


@app.websocket("/ws/peer-room/{code}")
async def peer_room_socket(websocket: WebSocket, code: str):
    origin = websocket.headers.get("origin")
    if origin and origin not in CORS_ORIGINS:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    db = SessionLocal()
    user = None
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=6)
        if not isinstance(auth, dict) or auth.get("type") != "authenticate" or not isinstance(auth.get("token"), str):
            await websocket.close(code=1008)
            return
        user = authenticate_websocket_token(auth["token"], db)
        if user is None:
            await websocket.close(code=1008)
            return
        prune_peer_rooms()
        room = peer_rooms.get(code)
        if room is None:
            await websocket.send_json({"type": "error", "message": "Room not found or expired."})
            await websocket.close(code=1008)
            return
        if user.id not in room["sockets"] and len(room["sockets"]) >= 2:
            await websocket.send_json({"type": "error", "message": "This room already has two learners."})
            await websocket.close(code=1008)
            return
        room["aliases"].setdefault(user.id, "Learner A" if not room["aliases"] else "Learner B")
        room["sockets"][user.id] = websocket
        await peer_broadcast(room, {"type": "state", "participants": [room["aliases"][uid] for uid in room["sockets"]],
                                    "subject": room["subject"], "code": room["code"], "messages": room["messages"][-20:]})
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            if data.get("type") == "chat":
                content = data.get("content")
                if not isinstance(content, str) or not content.strip() or len(content) > MAX_PEER_MESSAGE_CHARS:
                    await websocket.send_json({"type": "error", "message": "Message must be 1–2000 characters."})
                    continue
                entry = {"alias": room["aliases"][user.id], "content": content.strip()}
                room["messages"] = (room["messages"] + [entry])[-20:]
                await peer_broadcast(room, {"type": "message", **entry})
                if len(room["sockets"]) == 2:
                    try:
                        note = await asyncio.to_thread(facilitate_peer_debugging, room["subject"], room["messages"], room["code"])
                        await peer_broadcast(room, {"type": "facilitator", "content": note})
                    except Exception:
                        logging.getLogger(__name__).info("Peer facilitator unavailable", exc_info=True)
            elif data.get("type") == "code_update":
                code_text = data.get("code")
                if not isinstance(code_text, str) or len(code_text) > MAX_PEER_CODE_CHARS:
                    await websocket.send_json({"type": "error", "message": "Shared code must be at most 8000 characters."})
                    continue
                room["code"] = code_text
                await peer_broadcast(room, {"type": "code_update", "alias": room["aliases"][user.id], "code": code_text})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        logging.getLogger(__name__).exception("Peer room socket failed")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if user:
            room = peer_rooms.get(code)
            if room:
                if room["sockets"].get(user.id) is websocket:
                    room["sockets"].pop(user.id, None)
                if room["sockets"]:
                    await peer_broadcast(room, {"type": "state", "participants": [room["aliases"][uid] for uid in room["sockets"]],
                                                "subject": room["subject"], "code": room["code"], "messages": room["messages"][-20:]})
        db.close()


@app.get("/api/conversations")
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .filter(Conversation.messages.any(Message.role == "user"))
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    updated_titles = False
    for conversation in conversations:
        if conversation.title != "New Conversation":
            continue
        first_user_message = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id, Message.role == "user")
            .order_by(Message.created_at.asc(), Message.id.asc())
            .first()
        )
        if first_user_message and first_user_message.content.strip():
            conversation.title = conversation_title_from_message(first_user_message.content)
            updated_titles = True
    if updated_titles:
        db.commit()

    return [
        {
            "id": conversation.id,
            "user_id": conversation.user_id,
            "title": conversation.title,
            "subject": conversation.subject,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        }
        for conversation in conversations
    ]


@app.get("/api/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )

    # Earlier streaming versions saved messages without parent links. Rebuild their
    # original linear order once so branch selection can continue from old chats.
    if messages and all(message.parent_message_id is None for message in messages):
        previous_id = None
        for message in messages:
            message.parent_message_id = previous_id
            previous_id = message.id
        db.commit()

    return {
        "id": conversation.id,
        "user_id": conversation.user_id,
        "title": conversation.title,
        "subject": conversation.subject,
        "support_level": conversation.frustration_score,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "messages": [
            {
                "id": message.id,
                "conversation_id": message.conversation_id,
                "role": message.role,
                "content": message.content,
                "parent_message_id": message.parent_message_id,
                "created_at": message.created_at,
            }
            for message in messages
        ],
    }


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
        .first()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conversation)
    db.commit()
    return {"deleted": True, "conversation_id": conversation_id}


def get_syllabus_context_for_subject(db: Session, user_id: int, subject: str) -> str | None:
    mapping = (
        db.query(SyllabusMapping)
        .filter(SyllabusMapping.user_id == user_id, SyllabusMapping.subject == subject)
        .order_by(SyllabusMapping.created_at.desc())
        .first()
    )
    if not mapping:
        return None

    parts = [f"Module: {mapping.module}", f"Chapter: {mapping.chapter}"]
    if mapping.persona and mapping.persona.strip():
        parts.append(f"Persona: {mapping.persona.strip()}")
    return " | ".join(parts)


STREAM_END = object()


def next_stream_chunk(stream):
    try:
        return next(stream)
    except StopIteration:
        return STREAM_END


@app.get("/api/chat/stream")
async def stream_chat(
    message: str = Query(min_length=1, max_length=MAX_CHAT_CHARS),
    subject: str = Query(min_length=1, max_length=100),
    conversation_id: int | None = None,
    parent_message_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = None
    if conversation_id is not None:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
            .first()
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation.subject != subject:
            raise HTTPException(
                status_code=409,
                detail="This conversation belongs to a different subject. Start a new chat to switch subjects.",
            )

    if conversation is None:
        conversation = Conversation(
            user_id=current_user.id,
            title="New Conversation",
            subject=subject,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    if conversation.title == "New Conversation":
        first_user_message = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id, Message.role == "user")
            .order_by(Message.created_at.asc(), Message.id.asc())
            .first()
        )
        title_source = first_user_message.content if first_user_message else message
        if title_source.strip():
            conversation.title = conversation_title_from_message(title_source)

    prior_messages = get_message_path(db, conversation.id, parent_message_id)
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=message,
        parent_message_id=parent_message_id,
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    conversation_history = [
        {"role": item.role, "content": item.content} for item in prior_messages
    ]
    support_score, loop_count = estimate_support_level(message, conversation_history, conversation.frustration_score)
    conversation.frustration_score = support_score
    conversation.consecutive_loops = loop_count
    db.commit()
    syllabus_context = get_syllabus_context_for_subject(db, current_user.id, conversation.subject)

    async def event_generator():
        logging.getLogger(__name__).info("Generating Socratic response for subject %s", conversation.subject)

        collected_chunks: List[str] = []
        generation_error = None
        try:
            stream = iter(generate_socratic_response_stream(
                subject=conversation.subject,
                message=message,
                history=conversation_history,
                syllabus_context=syllabus_context,
                support_level=support_score,
            ))
            while True:
                chunk = await asyncio.to_thread(next_stream_chunk, stream)
                if chunk is STREAM_END:
                    break
                collected_chunks.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except Exception:
            logging.getLogger(__name__).exception("Chat response streaming failed")
            generation_error = (
                "The local tutor could not complete this response. Check that Ollama is running "
                "and the configured model is installed, then try again."
            )
            yield f"data: {json.dumps({'error': generation_error})}\n\n"

        full_reply = "".join(collected_chunks)
        if generation_error:
            full_reply = f"{full_reply.rstrip()}\n\n{generation_error}".strip()
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=full_reply,
            parent_message_id=user_message.id,
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        if not mismatched_subject(message, conversation.subject):
            asyncio.create_task(classify_and_store_misconception(
                current_user.id, conversation.id, user_message.id, message, full_reply
            ))

        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        yield f"data: {json.dumps({'done': True, 'conversation_id': conversation.id, 'user_message_id': user_message.id, 'assistant_message_id': assistant_message.id, 'support_level': support_score, 'error': generation_error})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat/stream")
async def stream_chat_post(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """POST variant keeps long prompts and attached text out of the request URL."""
    return await stream_chat(
        message=data.message,
        subject=data.subject,
        conversation_id=data.conversation_id,
        parent_message_id=data.parent_message_id,
        current_user=current_user,
        db=db,
    )


@app.post("/api/chat")
def chat_with_tutor(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = None
    if data.conversation_id is not None:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == data.conversation_id, Conversation.user_id == current_user.id)
            .first()
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation.subject != data.subject:
            raise HTTPException(
                status_code=409,
                detail="This conversation belongs to a different subject. Start a new chat to switch subjects.",
            )

    if conversation is None:
        conversation = Conversation(
            user_id=current_user.id,
            title="New Conversation",
            subject=data.subject,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    if conversation.title == "New Conversation":
        first_user_message = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id, Message.role == "user")
            .order_by(Message.created_at.asc(), Message.id.asc())
            .first()
        )
        title_source = first_user_message.content if first_user_message else data.message
        if title_source.strip():
            conversation.title = conversation_title_from_message(title_source)

    prior_messages = get_message_path(db, conversation.id, data.parent_message_id)
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=data.message,
        parent_message_id=data.parent_message_id,
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    conversation_history = [
        {"role": item.role, "content": item.content} for item in prior_messages
    ]
    support_score, loop_count = estimate_support_level(data.message, conversation_history, conversation.frustration_score)
    conversation.frustration_score = support_score
    conversation.consecutive_loops = loop_count
    db.commit()

    syllabus_context = get_syllabus_context_for_subject(db, current_user.id, conversation.subject)
    print(f"Generating Socratic response for: {conversation.subject}...")
    socratic_reply = generate_socratic_response(
        subject=conversation.subject,
        message=data.message,
        history=conversation_history,
        syllabus_context=syllabus_context,
        support_level=support_score,
    )

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=socratic_reply,
        parent_message_id=user_message.id,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    if not mismatched_subject(data.message, conversation.subject):
        log_misconception(db, current_user.id, conversation.id, user_message.id, data.message, socratic_reply)

    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"reply": socratic_reply, "conversation_id": conversation.id, "support_level": support_score}


@app.post("/api/messages/{message_id}/edit")
def edit_message(
    message_id: int,
    data: MessageEditRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    original_message = (
        db.query(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Message.id == message_id, Conversation.user_id == current_user.id)
        .first()
    )
    if original_message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if original_message.role != "user":
        raise HTTPException(status_code=400, detail="Only student messages can be edited")

    conversation = original_message.conversation
    replacement = Message(
        conversation_id=conversation.id,
        role="user",
        content=data.content,
        parent_message_id=message_id,
    )
    db.add(replacement)
    db.commit()
    db.refresh(replacement)

    if data.regenerate:
        prior_messages = get_message_path(db, conversation.id, original_message.parent_message_id)
        history = [{"role": item.role, "content": item.content} for item in prior_messages]
        reply = generate_socratic_response(
            subject=conversation.subject,
            message=replacement.content,
            history=history,
            syllabus_context=get_syllabus_context_for_subject(db, current_user.id, conversation.subject),
        )
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=reply,
            parent_message_id=replacement.id,
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)

    original_message.conversation.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "id": replacement.id,
        "conversation_id": replacement.conversation_id,
        "role": replacement.role,
        "content": replacement.content,
        "parent_message_id": replacement.parent_message_id,
        "assistant_message_id": assistant_message.id if data.regenerate else None,
    }


@app.post("/api/auth/register", response_model=UserResponse)
def register_user(user_data: UserRegisterRequest, db: Session = Depends(get_db)):
    normalized_email = user_data.email.lower().strip()
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        role = normalize_user_role(user_data.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if role == "faculty":
        invite_code = os.getenv("STEPWISE_FACULTY_INVITE_CODE", "")
        if not invite_code or not hmac.compare_digest(user_data.faculty_invite_code or "", invite_code):
            raise HTTPException(status_code=403, detail="A valid faculty invitation is required")

    user = User(
        email=normalized_email,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=TokenResponse)
def login_user(user_data: UserLoginRequest, db: Session = Depends(get_db)):
    normalized_email = user_data.email.lower().strip()
    user = db.query(User).filter(User.email == normalized_email).first()
    if not user or not user.is_active or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = create_access_token(
        {
            "sub": user.email,
            "role": user.role,
            "password_version": password_reset_version(user),
        }
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/auth/password-reset/request")
def request_password_reset(
    request: PasswordResetRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    email_delivery_available = password_reset_email_configured()
    if not email_delivery_available and not is_loopback_request(http_request):
        raise HTTPException(
            status_code=503,
            detail="Password reset requires email delivery when accessed remotely. Configure SMTP or open StepWise on this computer.",
        )

    email = request.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if user:
        token = create_password_reset_token(user)
        frontend_url = os.getenv("STEPWISE_FRONTEND_URL", "http://localhost:5173").rstrip("/")
        reset_url = f"{frontend_url}/?reset_token={quote(token, safe='')}"
        if email_delivery_available:
            try:
                send_password_reset_email(user.email, reset_url)
            except Exception as exc:
                logging.getLogger(__name__).exception("Password reset email delivery failed")
                raise HTTPException(
                    status_code=503,
                    detail="The reset email could not be sent. Check the SMTP settings and try again.",
                ) from exc
        elif is_loopback_request(http_request):
            return {
                "message": "Email is not configured. Use the local password reset link below; it expires in 15 minutes.",
                "reset_url": reset_url,
            }

    return {
        "message": "If an account exists for that email, a password reset link has been sent."
    }


@app.post("/api/auth/password-reset/confirm")
def confirm_password_reset(
    request: PasswordResetConfirmRequest,
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(request.token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "password_reset":
            raise HTTPException(status_code=400, detail="Invalid or expired reset link")

        email = payload.get("sub")
        user = db.query(User).filter(User.email == email).first()
        if user is None or not hmac.compare_digest(
            payload.get("password_version", ""), password_reset_version(user)
        ):
            raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link") from exc

    user.hashed_password = get_password_hash(request.new_password)
    db.commit()
    return {"message": "Password updated. You can now sign in with your new password."}


@app.get("/api/users/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return current_user
