# github-slm-reviewer

A GitHub webhook server that uses a local SLM (Small Language Model) via Ollama to review pull requests.

## Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | FastAPI webhook server + scaffolding | In progress |
| 2 | GitHub API — fetch PR diff | Planned |
| 3 | Ollama inference — analyse diff | Planned |
| 4 | Supabase — persist review results | Planned |

## Setup

```bash
cp .env.example .env
# fill in values in .env

pip3 install -r requirements.txt
uvicorn app.main:app --reload
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhook` | Receives GitHub webhook events |
| GET | `/health` | Server + Ollama reachability check |

## Running tests

```bash
# start server in one terminal
uvicorn app.main:app --reload

# in another terminal
python tests/test_webhook.py
```

## Model

Runs `qwen2.5-coder:3b` via [Ollama](https://ollama.com) locally.
