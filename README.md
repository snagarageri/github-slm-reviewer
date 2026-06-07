# github-slm-reviewer

A self-hosted GitHub PR reviewer that runs entirely on your machine. It uses a local Small Language Model (SLM) via Ollama to analyse pull request diffs and post inline code review comments — no cloud AI API required.

## Architecture

```
 GitHub                ngrok                 Your machine
 ──────                ─────                 ────────────

 PR opened  ─────────▶  tunnel  ──────────▶  FastAPI :8000
 or sync'd              (HTTPS)              POST /webhook
                                              │  (returns 200 immediately)
 ◀─ review  ◀──────────────────────────────  │
    comments                                  │ BackgroundTask: review_pr()
                                              │
                          ┌───────────────────┤
                          │                   │
                  ┌───────▼──────┐   ┌────────▼────────┐
                  │  GitHub API  │   │  Ollama (local)  │
                  │              │   │  qwen2.5-coder   │
                  │ get_pr_files │   │  analyze_file()  │
                  │ post_comment │   └─────────────────┘
                  └───────┬──────┘
                          │
                   ┌──────▼──────┐
                   │  Supabase   │
                   │             │
                   │  pr_states  │  ← tracks iteration, open/resolved counts
                   │  issues     │  ← deduplicates across pushes
                   └─────────────┘
```

### Recursive review loop

Each time a PR is **opened** or **pushed to** (`synchronize`), the reviewer:

1. Fetches the diff for every `.py / .js / .ts / .go / .java` file
2. Sends each file's patch to `qwen2.5-coder:3b` via Ollama — asking for JSON-structured issues
3. **Deduplicates** by fingerprint `(filename : line : category)`:
   - Issue not seen before → post inline comment + save to Supabase
   - Issue already open → skip (no duplicate comment)
   - Issue was open, now gone → mark as **fixed** in Supabase
4. Posts a summary comment on the PR with issue counts and iteration number
5. Bumps the iteration counter in Supabase

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.9+ | system or [python.org](https://python.org) |
| Ollama | latest | [ollama.com](https://ollama.com) — install the `.dmg` app on Mac |
| ngrok | latest | [ngrok.com](https://ngrok.com/download) |
| Supabase | — | free project at [supabase.com](https://supabase.com) |

---

## Installation

```bash
git clone https://github.com/<you>/github-slm-reviewer
cd github-slm-reviewer

pip3 install -r requirements.txt
```

### Pull the model

```bash
ollama pull qwen2.5-coder:3b
```

### Set up Supabase

1. Create a free project at [supabase.com](https://supabase.com)
2. Open **SQL Editor** and paste the contents of `supabase_schema.sql`, then run it

---

## Configuration

```bash
cp .env.example .env
```

Edit `.env`:

```env
# GitHub — create a Personal Access Token with repo + webhooks scope
GITHUB_TOKEN=ghp_...
GITHUB_REPO=owner/repo          # the repo to watch (used by setup_webhook.py)
GITHUB_WEBHOOK_SECRET=          # any random string, e.g.: openssl rand -hex 20

# Supabase — from Project Settings → API
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<anon-public-key>

# Ollama (defaults work if Ollama app is running)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:3b

# Filled in after you start ngrok (used by setup_webhook.py)
WEBHOOK_URL=https://<your-id>.ngrok-free.app/webhook
```

---

## Running

### Step 1 — Start the server

```bash
bash run.sh
```

This starts `uvicorn` on port 8000 and prints instructions.

### Step 2 — Expose it via ngrok

In a **separate terminal**:

```bash
ngrok http 8000
```

Copy the `Forwarding` HTTPS URL (e.g. `https://abc123.ngrok-free.app`).

### Step 3 — Register the GitHub webhook

```bash
python3 setup_webhook.py https://abc123.ngrok-free.app/webhook
```

Or set `WEBHOOK_URL` in `.env` and run without arguments:

```bash
python3 setup_webhook.py
```

### Step 4 — Open a PR

Open or push to a PR in the configured repo. Watch the server logs — within seconds you'll see the analysis running and inline comments appearing on the PR.

---

## Smoke test (local only)

With the server running, verify the webhook endpoint accepts signed payloads:

```bash
python3 scripts/smoke_test.py
```

This sends a fake `pull_request` event signed with your `GITHUB_WEBHOOK_SECRET`. The server returns 200 immediately; the background `review_pr()` task will attempt GitHub API calls (which will fail for the fake repo, but all logging is visible).

---

## Project structure

```
github-slm-reviewer/
├── app/
│   ├── main.py               # FastAPI app — /webhook + /health
│   ├── core/
│   │   └── reviewer.py       # CodeReviewer — orchestrates the full loop
│   ├── github/
│   │   ├── client.py         # PyGithub wrapper
│   │   ├── parser.py         # Diff parser, language detection
│   │   └── comments.py       # Comment formatters
│   ├── analysis/
│   │   ├── engine.py         # Ollama inference + JSON parsing
│   │   ├── prompts.py        # System + user prompt builders
│   │   └── chunker.py        # File filtering + patch chunking
│   └── state/
│       ├── manager.py        # Supabase read/write
│       └── models.py         # Pydantic models (PRState, Issue)
├── tests/                    # 70 unit tests (all mocked)
├── scripts/
│   └── smoke_test.py         # Local end-to-end smoke test
├── setup_webhook.py          # Register GitHub webhook
├── run.sh                    # Start uvicorn + print ngrok instructions
├── supabase_schema.sql       # Run once in Supabase SQL editor
├── requirements.txt
└── .env.example
```

---

## Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | FastAPI webhook server + scaffolding | ✅ Done |
| 2 | GitHub API — fetch diff, post comments | ✅ Done |
| 3 | Ollama SLM analysis engine | ✅ Done |
| 4 | Supabase state management | ✅ Done |
| 5 | Recursive review loop (wire everything) | ✅ Done |
| 6 | Go live — ngrok + webhook setup + smoke test | ✅ Done |
