# StepWise Project Diagrams

**Project:** StepWise — An Interactive Local Socratic Tutoring System Powered by Large Language Models  
**Prepared for:** Project design and academic review  
**Status:** Diagrams reflect the current codebase inspected on 11 November 2026.

> These diagrams describe the current implementation. They are written in Mermaid, which can be rendered by GitHub, VS Code extensions, Mermaid Live, and many Markdown tools. Features explicitly marked as future scope are not shown as implemented.

## 1. System context diagram

This context diagram shows the system boundary and external actors/services.

```mermaid
flowchart LR
    Student[Student]
    Faculty[Faculty]
    Browser[Web browser\nReact + Vite]
    API[StepWise backend\nFastAPI]
    DB[(SQLite database)]
    Ollama[Local Ollama service\nConfigured open-weight model]
    SMTP[SMTP email service\nOptional]

    Student -->|Questions, settings, attachments, account actions| Browser
    Faculty -->|Syllabus mappings, account actions| Browser
    Browser -->|HTTPS/JSON API requests, POST SSE stream, WebSocket| API
    API -->|JSON responses and streamed tutor text| Browser
    API -->|Read/write account, chat, syllabus, insight data| DB
    DB -->|Persisted records| API
    API -->|Prompt, history, subject, support level| Ollama
    Ollama -->|Generated Socratic response tokens| API
    API -.->|Password reset email when configured| SMTP
```

## 2. Data Flow Diagram (DFD)

### DFD Level 0 — system overview

```mermaid
flowchart LR
    Student[External entity: Student]
    Faculty[External entity: Faculty]
    Tutor((0. StepWise tutoring system))
    Store[(D1 SQLite data store)]
    Model[External service: Local Ollama model]
    Mail[External service: SMTP, optional]

    Student -->|Credentials, prompts, chat actions| Tutor
    Tutor -->|Auth result, tutor guidance, chat history, insights| Student
    Faculty -->|Credentials, syllabus information| Tutor
    Tutor -->|Auth result, mapping status| Faculty
    Tutor <-->|Users, conversations, messages, mappings, misconception records| Store
    Tutor -->|Socratic prompt and conversation context| Model
    Model -->|Generated tutor response| Tutor
    Tutor -.->|Reset email request, when configured| Mail
```

### DFD Level 1 — primary processes and data stores

```mermaid
flowchart LR
    Student[Student]
    Faculty[Faculty]
    P1((1. Account and access management))
    P2((2. Conversation and message management))
    P3((3. Socratic response generation))
    P4((4. Learning insight generation))
    P5((5. Peer room coordination))
    P6((6. Syllabus mapping management))
    D1[(D1 Users)]
    D2[(D2 Conversations and messages)]
    D3[(D3 Misconception logs)]
    D4[(D4 Syllabus mappings)]
    O[Local Ollama model]
    Email[SMTP service, optional]

    Student -->|Register, login, reset request| P1
    P1 <-->|Account and password data| D1
    P1 -.->|Reset email if SMTP is configured| Email
    P1 -->|Token/profile result| Student

    Student -->|Create, list, open, delete, edit chat| P2
    P2 <-->|Conversation and branched messages| D2
    P2 -->|Chat history and branch view| Student
    P2 -->|Prompt, subject, history, support level| P3
    P3 <-->|Model request and generated response| O
    P3 -->|Tutor response tokens over SSE| Student
    P3 -->|User prompt and response for classification| D3

    Student -->|Request learning insights| P4
    P4 <-->|Learner's misconception records| D3
    P4 -->|Friendly pattern labels and next-step tips| Student

    Student -->|Create/join room, chat, code updates| P5
    P5 -->|Ephemeral room events, participant aliases| Student

    Faculty -->|Create/list subject mappings| P6
    P6 <-->|Mapping records| D4
    P6 -->|Mapping list/status| Faculty
    D4 -->|Optional subject/module/chapter context| P3
```

**DFD data-store notes:** accounts, conversations, messages, syllabus mappings, and misconception logs are SQLAlchemy records stored in SQLite. Peer-room membership, code updates, and live messages are held in backend memory and expire; they are not persistent SQLite records. Attachment contents are extracted in the browser and included in the chat message text; the app has no separate file-storage data store.

## 3. Entity-Relationship Diagram (ERD)

This ERD follows the SQLAlchemy models in `models.py`. `PK` means primary key and `FK` means foreign key.

```mermaid
erDiagram
    USERS {
        int id PK
        string email UK
        string full_name
        string hashed_password
        string role
        boolean is_active
        datetime created_at
    }
    CONVERSATIONS {
        int id PK
        int user_id FK
        string title
        string subject
        int frustration_score
        int consecutive_loops
        datetime created_at
        datetime updated_at
    }
    MESSAGES {
        int id PK
        int conversation_id FK
        int parent_message_id FK
        string role
        text content
        datetime created_at
    }
    SYLLABUS_MAPPINGS {
        int id PK
        int user_id FK
        string subject
        string module
        string chapter
        text persona
        datetime created_at
    }
    MISCONCEPTION_LOGS {
        int id PK
        int user_id FK
        int conversation_id FK
        int source_message_id FK
        string category_code
        float confidence
        boolean is_sample
        datetime created_at
    }

    USERS ||--o{ CONVERSATIONS : owns
    CONVERSATIONS ||--o{ MESSAGES : contains
    MESSAGES o|--o{ MESSAGES : parent_of
    USERS ||--o{ SYLLABUS_MAPPINGS : creates
    USERS ||--o{ MISCONCEPTION_LOGS : receives
    CONVERSATIONS ||--o{ MISCONCEPTION_LOGS : has
    MESSAGES o|--o{ MISCONCEPTION_LOGS : source_for
```

**Relationship notes:** A message's `parent_message_id` points to another message in the same message tree, allowing alternative branches. A misconception record's source message is optional (`SET NULL` on deletion); its user and conversation references are required. Deleting a user or conversation cascades through the relevant owned records as configured by the models/database.

## 4. UML Use-Case Diagram

```mermaid
flowchart LR
    Student[Student]
    Faculty[Faculty]
    UseCases((StepWise))
    U1([Register and sign in])
    U2([Request/reset password])
    U3([Create and manage conversations])
    U4([Ask a question and receive streamed Socratic guidance])
    U5([Attach text, code, or selectable-text PDF])
    U6([Use browser speech-to-text])
    U7([Edit a message and explore a branch])
    U8([View learning insights])
    U9([Create/join a temporary peer room])
    U10([Manage syllabus mappings])

    Student --- U1
    Student --- U2
    Student --- U3
    Student --- U4
    Student --- U5
    Student --- U6
    Student --- U7
    Student --- U8
    Student --- U9
    Faculty --- U1
    Faculty --- U2
    Faculty --- U10
    U4 -. uses local inference .-> Model[(Ollama model)]
    U8 -. reads .-> Data[(Misconception records)]
```

## 5. UML Class Diagram

The domain portion models persisted entities. Service components are included to show the major runtime responsibilities.

```mermaid
classDiagram
    class User {
      +int id
      +string email
      +string full_name
      +string hashed_password
      +string role
      +bool is_active
      +datetime created_at
    }
    class Conversation {
      +int id
      +int user_id
      +string title
      +string subject
      +int frustration_score
      +int consecutive_loops
      +datetime created_at
      +datetime updated_at
    }
    class Message {
      +int id
      +int conversation_id
      +int parent_message_id
      +string role
      +text content
      +datetime created_at
    }
    class SyllabusMapping {
      +int id
      +int user_id
      +string subject
      +string module
      +string chapter
      +text persona
    }
    class MisconceptionLog {
      +int id
      +int user_id
      +int conversation_id
      +int source_message_id
      +string category_code
      +float confidence
      +bool is_sample
    }
    class StepWiseAPI {
      +authenticate()
      +manage_conversations()
      +stream_chat()
      +edit_message()
      +get_learning_insights()
      +manage_peer_rooms()
    }
    class SocraticEngine {
      +generate_response()
      +generate_response_stream()
      +classify_misconception()
      +facilitate_peer_debugging()
    }
    class LearningSupport {
      +estimate_support_level()
    }
    class OllamaService {
      +chat(model, messages, options)
    }

    User "1" --> "0..*" Conversation : owns
    Conversation "1" *-- "0..*" Message : contains
    Message "0..1" --> "0..*" Message : parent/children
    User "1" --> "0..*" SyllabusMapping : creates
    User "1" --> "0..*" MisconceptionLog : has
    Conversation "1" --> "0..*" MisconceptionLog : records
    Message "0..1" --> "0..*" MisconceptionLog : source
    StepWiseAPI ..> SocraticEngine : calls
    StepWiseAPI ..> LearningSupport : calculates learner support
    SocraticEngine ..> OllamaService : invokes local model
```

## 6. UML Sequence Diagram — streamed tutoring exchange

```mermaid
sequenceDiagram
    actor Student
    participant UI as React ChatInterface
    participant API as FastAPI /api/chat/stream
    participant DB as SQLite via SQLAlchemy
    participant Support as LearningSupport
    participant Engine as Socratic AI engine
    participant Ollama as Local Ollama model

    Student->>UI: Submit prompt and selected subject
    UI->>API: POST prompt, subject, conversation/branch IDs + bearer token
    API->>API: Validate token and request
    API->>DB: Verify conversation ownership or create conversation
    API->>DB: Load parent path and save user message
    API->>Support: Estimate support level and repeated-loop count
    Support-->>API: Support level
    API->>DB: Save conversation support state
    API->>DB: Load optional matching syllabus context
    API-->>UI: Start text/event-stream response
    API->>Engine: Prompt with subject, history, context, support level
    Engine->>Ollama: Stream local model generation
    loop For each generated token chunk
        Ollama-->>Engine: Text chunk
        Engine-->>API: Text chunk
        API-->>UI: SSE data chunk
        UI-->>Student: Render accumulating tutor response
    end
    API->>DB: Save complete assistant message as child of user message
    API-->>UI: SSE completion with conversation/message IDs
    API-)DB: Classify prompt/response and store misconception record (background task)
```

## 7. Scope represented by these diagrams

**Implemented and shown:** authentication, SQLite persistence, conversation history and deletion, message branching/editing, streaming tutor chat, local Ollama inference, adaptive support/frustration tracking, misconception insights, faculty syllabus mappings, temporary two-person peer rooms, browser speech-to-text, and text/code/PDF attachment text extraction.

**Future scope (not shown as implemented):** curriculum RAG with ChromaDB, a knowledge graph, Docker code execution sandbox, Whisper.cpp local speech recognition, image/vision input, persistent multi-user collaboration, and faculty telemetry/analytics dashboard.

**Attachment and voice limits:** PDF extraction supports selectable text, not scanned image-only pages. Browser speech-to-text depends on browser and microphone support; it is not the planned local Whisper.cpp engine. Peer-room messages/code are temporary in-memory data.
