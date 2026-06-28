# 🤖 Assistantpilot-AI

A **Slack-like real-time team collaboration platform** powered by a hybrid AI engine — combining **spaCy NLP** for message intelligence and **Google Gemini AI** as an intelligent project lead assistant that recommends task assignments, detects risks, and chats directly in channels.

---

## 📌 Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Environment Variables](#environment-variables)
- [Running the App](#running-the-app)
- [API Reference](#api-reference)
- [AI System Guide](#ai-system-guide)
- [GitHub Integration](#github-integration)
- [Database Models](#database-models)

---

## ✨ Features

### 💬 Real-Time Chat
- WebSocket-based live messaging (Django Channels + Daphne ASGI)
- Channel & Direct Message support
- Threaded replies
- Message reactions (emoji)
- Typing indicators
- File attachments
- Pinned messages
- Online presence indicators

### 🤖 Hybrid AI Engine
- **spaCy NLP** — intent detection, entity extraction, sentiment analysis, auto-tagging
- **Gemini AI (gemini-2.5-flash)** — project lead assistant that recommends task assignments, provides project insights, and detects risks
- **AI Chat Bot** — `@ai` in any channel to chat directly with PilotAI bot in real time

### 📊 Project Management
- Workspace & channel management
- Calendar/events with auto-scheduling from chat messages
- Team performance metrics (efficiency, reliability, task tracking)
- HR profile system with employee levels and skill tracking

### 🐙 GitHub Integration
- Link a GitHub repository to any workspace
- Live project report: commits, open PRs, issues, contributors
- Admin-only repository linking

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (HTML/CSS/JS)             │
│              Served via Python HTTP server           │
│                   localhost:3000                     │
└───────────────────┬─────────────────────────────────┘
                    │ REST API + WebSocket
┌───────────────────▼─────────────────────────────────┐
│              Django Backend (Daphne ASGI)            │
│                   localhost:8000                     │
│                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  spaCy NLP  │  │ Gemini API   │  │ GitHub API │  │
│  │ ai_service  │  │gemini_service│  │github_svc  │  │
│  └─────────────┘  └──────────────┘  └────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │          Django ORM + SQLite DB              │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### AI Decision Flow (Hybrid)
```
Backend collects structured data (team, tasks, metrics)
         ↓
Backend filters valid candidates for a task
         ↓
Gemini receives filtered data → suggests best assignment + reason
         ↓
Backend validates suggestion (DB check)
         ↓
Backend executes (updates UserProfile + creates CalendarEvent)
         ↓
Response returned to user in natural language
```

> ⚠️ Gemini **never** directly modifies the database. All AI suggestions are validated by the backend before execution.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend Framework | Django 4.2.7 |
| ASGI Server | Daphne 4.0.0 |
| WebSockets | Django Channels 4.0.0 |
| REST API | Django REST Framework 3.14.0 |
| NLP Engine | spaCy 3.7.2 + `en_core_web_sm` |
| AI / LLM | Google Gemini API (`gemini-2.5-flash`) |
| GitHub Integration | GitHub REST API v3 |
| Database | SQLite (dev) |
| Authentication | Token-based (DRF AuthToken) |
| CORS | django-cors-headers |
| Frontend | Vanilla HTML / CSS / JavaScript |

---

## 📂 Project Structure

```
pilot-ai/
├── README.md
└── backend/
    ├── manage.py
    ├── requirements.txt
    ├── .env                        # Environment variables (not committed)
    ├── .gitignore
    ├── db.sqlite3                  # SQLite database
    ├── backend/
    │   ├── settings.py             # Django settings
    │   ├── urls.py                 # Root URL configuration
    │   ├── asgi.py                 # ASGI app (WebSocket support)
    │   └── wsgi.py
    ├── slack_app/
    │   ├── models.py               # DB models (Workspace, Channel, Message, etc.)
    │   ├── views.py                # REST API views + Gemini endpoints
    │   ├── consumers.py            # WebSocket consumer + AI bot auto-reply
    │   ├── serializers.py          # DRF serializers
    │   ├── ai_service.py           # spaCy NLP: intent, sentiment, tags
    │   ├── gemini_service.py       # Google Gemini AI: task assignment, insights, risks
    │   ├── github_service.py       # GitHub API: commits, PRs, issues
    │   ├── routing.py              # WebSocket URL routing
    │   └── migrations/
    └── frontend/
        ├── index.html              # Main SPA
        ├── css/
        │   └── style.css
        └── js/
            └── app.js
```

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.10+
- pip
- Git

### 1. Clone the repository

```bash
git clone https://github.com/chetankhadse21/Assistantpilot-AI.git
cd Assistantpilot-AI/backend
```

### 2. Create a virtual environment

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Download spaCy language model

```bash
python -m spacy download en_core_web_sm
```

### 5. Set up environment variables

Create a `.env` file in the `backend/` directory:

```env
SECRET_KEY=your-django-secret-key-here
GITHUB_TOKEN=your_github_personal_access_token
GEMINI_API_KEY=your_gemini_api_key
```

### 6. Run migrations

```bash
python manage.py migrate
```

### 7. Create a superuser (optional, for admin panel)

```bash
python manage.py createsuperuser
```

---

## 🔐 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key |
| `GITHUB_TOKEN` | ✅ | GitHub Personal Access Token (for repo integration) |
| `GEMINI_API_KEY` | ✅ | Google Gemini API key |

---

## 🚀 Running the App

### Start Django backend

```bash
cd backend
python manage.py runserver
```

Backend runs at: `http://127.0.0.1:8000`

### Start frontend

```bash
cd backend/frontend
python -m http.server 3000
```

Frontend runs at: `http://localhost:3000`

---

## 📡 API Reference

All API endpoints require `Authorization: Token <your_token>` header unless noted.

### 🔐 Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register/` | Register a new user |
| POST | `/api/auth/login/` | Login and get token |
| POST | `/api/auth/logout/` | Logout |
| GET/PUT | `/api/auth/me/` | Get/update current user profile |

### 🏢 Workspaces

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/workspaces/` | List / create workspaces |
| GET/PUT/DELETE | `/api/workspaces/<id>/` | Workspace detail |
| GET | `/api/workspaces/<id>/members/` | List workspace members |
| PATCH | `/api/workspaces/<id>/set-repo/` | Link GitHub repo (admin only) |

### 📢 Channels

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/workspaces/<ws_id>/channels/` | List / create channels |
| POST | `/api/workspaces/<ws_id>/channels/<id>/join/` | Join a channel |
| GET | `/api/workspaces/<ws_id>/channels/<id>/members/` | Channel members |
| GET | `/api/workspaces/<ws_id>/channels/<id>/pins/` | Pinned messages |
| GET | `/api/workspaces/<ws_id>/channels/<id>/summary/` | AI channel activity summary |

### 💬 Messages

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/channels/<ch_id>/messages/` | List / send channel messages |
| GET/POST | `/api/dms/<dm_id>/messages/` | List / send DM messages |
| POST | `/api/channels/<ch_id>/messages/<id>/react/` | Toggle emoji reaction |
| POST | `/api/channels/<ch_id>/messages/<id>/pin/` | Pin a message |
| GET | `/api/channels/<ch_id>/messages/<id>/thread/` | Get thread replies |

### 🤖 AI Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/ai/analyze/` | Analyze message intent, sentiment, tags |
| GET | `/api/ai/search/?q=<query>&workspace=<id>` | AI-powered smart search |
| POST | `/api/ai/assign-task/` | Gemini task assignment recommendation |
| GET | `/api/ai/project-insights/?workspace=<id>` | Gemini project summary |
| GET | `/api/ai/detect-risks/?workspace=<id>` | Gemini risk detection |

### 🐙 GitHub

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/github/report/?workspace=<id>` | Live GitHub project report |

### 📅 Calendar

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/workspaces/<ws_id>/events/` | List / create calendar events |

### 🔌 WebSocket

```
ws://127.0.0.1:8000/ws/chat/<room_name>/?token=<auth_token>
```

Room name format:
- Channel: `channel_<id>`
- Direct Message: `dm_<id>`

---

## 🤖 AI System Guide

### spaCy NLP (Automatic — no setup needed)

Every message is automatically analyzed by spaCy:
- **Intent Detection**: `question`, `task`, `meeting`, `announcement`, `help`, `praise`, `general`
- **Sentiment Analysis**: `positive`, `negative`, `neutral`
- **Entity & Tag Extraction**: mentions, dates, keywords, organizations
- **Auto-Calendar**: Messages with `meeting` or `task` intent + a date are auto-created as calendar events

### Gemini AI — REST Endpoints

**Assign a Task:**
```bash
curl -X POST http://127.0.0.1:8000/api/ai/assign-task/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Build authentication API", "workspace_id": 1}'
```

**Project Insights:**
```bash
curl http://127.0.0.1:8000/api/ai/project-insights/?workspace=1 \
  -H "Authorization: Token <token>"
```

**Detect Risks:**
```bash
curl http://127.0.0.1:8000/api/ai/detect-risks/?workspace=1 \
  -H "Authorization: Token <token>"
```

### 💬 PilotAI Chat Bot

Type in any channel to chat with the AI directly:

| Trigger | Example |
|---|---|
| `@ai` | `@ai who should work on the payment module?` |
| `@pilotai` | `@pilotai summarize this week's progress` |
| `/ai` | `/ai what are the current risks?` |
| `!ai` | `!ai explain JWT authentication` |

PilotAI will show a typing indicator and reply within seconds.

---

## 🐙 GitHub Integration

1. An **admin** links a GitHub repo to a workspace via:
   ```
   PATCH /api/workspaces/<id>/set-repo/
   {"github_repo": "owner/repo-name"}
   ```

2. Anyone can then fetch the live project report:
   ```
   GET /api/github/report/?workspace=<id>
   ```

The report includes:
- Repository metadata (stars, forks, language)
- Last 5 commits with author and date
- Open pull requests
- Open issues
- Top 5 contributors

---

## 🗄️ Database Models

| Model | Description |
|---|---|
| `Workspace` | Team workspace with optional GitHub repo link |
| `WorkspaceMember` | User ↔ Workspace membership with role (admin/member/guest) |
| `Channel` | Public or private channels within a workspace |
| `DirectMessage` | 1-on-1 DM conversation between two users |
| `Message` | Chat message with AI-analyzed fields (intent, sentiment, tags) |
| `Reaction` | Emoji reactions on messages |
| `UserProfile` | Extended profile: skills, performance metrics (efficiency, reliability) |
| `PinnedMessage` | Pinned messages in channels |
| `CalendarEvent` | Meetings and deadlines, auto-created from AI-detected messages |

---

## 🔒 Security Notes

- `.env`, `db.sqlite3`, `__pycache__/`, and `venv/` are in `.gitignore` and never committed
- Gemini AI cannot directly modify the database — all decisions are validated by the backend first
- GitHub token is stored server-side only
- All API endpoints require token authentication except register/login

---

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.