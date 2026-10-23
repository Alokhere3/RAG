# Local Development Guide

This document outlines local environment setup, testing, linting, and database operations.

## 1. Prerequisites

Ensure the following tools are installed:
- **Python**: 3.13+
- **Node.js**: 24+
- **Docker & Docker Compose**: Docker 28+, Compose v2+
- **Git**

---

## 2. Environment Setup

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure required values such as `DATABASE_URL` and `REDIS_URL` match your local development environment.

---

## 3. Backend Setup

From the repository root:

```bash
# 1. Navigate to backend
cd backend

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

---

## 4. Frontend Setup

From the repository root:

```bash
# 1. Navigate to frontend
cd frontend

# 2. Install dependencies
npm install

# 3. Start development server
npm run dev
```

---

## 5. Docker Orchestration

To run all dependencies (PostgreSQL with pgvector, Redis, Backend, Frontend):

```bash
docker compose up -d
```

To stop containers:
```bash
docker compose down
```

---

## 6. Database Migrations (Alembic)

Database schema migrations are managed via Alembic:

```bash
cd backend

# Run pending migrations
alembic upgrade head

# Roll back last migration
alembic downgrade -1

# Create new migration autogeneration (Future phases)
alembic revision --autogenerate -m "description_of_changes"
```

---

## 7. Testing & Quality Assurance

### Backend Tests
```bash
cd backend
pytest -v
```

### Frontend Tests
```bash
cd frontend
npm test
```

### Code Formatting & Linting
- **Backend**: `ruff check .` / `ruff format .`
- **Frontend**: `npm run lint`
