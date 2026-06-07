#!/usr/bin/env bash
# Start the github-slm-reviewer FastAPI server.
# Run ngrok in a separate terminal to expose it to GitHub.

set -euo pipefail

PORT="${PORT:-8000}"

echo "=================================================="
echo "  github-slm-reviewer"
echo "=================================================="
echo ""
echo "  Server → http://localhost:${PORT}"
echo ""
echo "  In a SEPARATE terminal, expose it via ngrok:"
echo ""
echo "    ngrok http ${PORT}"
echo ""
echo "  Then register the webhook (replace URL with your ngrok URL):"
echo ""
echo "    python3 setup_webhook.py https://<your-id>.ngrok-free.app/webhook"
echo ""
echo "=================================================="
echo ""

python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --reload
