from __future__ import annotations

import json
import logging
import os
import re

import ollama
from dotenv import load_dotenv

from app.analysis.prompts import SYSTEM_PROMPT, build_user_prompt
from app.github.parser import get_language

load_dotenv()

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> str:
    """Strip markdown fences and extract the first JSON object from text."""
    # remove ```json ... ``` or ``` ... ```
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    m = _JSON_RE.search(text)
    return m.group(0) if m else text


class AnalysisEngine:
    def __init__(self, model: str | None = None, base_url: str | None = None):
        self._model = model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
        host = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._client = ollama.Client(host=host)

    def analyze_file(self, filename: str, language: str, patch: str) -> dict:
        """Call the SLM and return parsed analysis.

        Returns a dict with keys: issues, overall_score, summary.
        On any error, returns a safe empty result rather than raising.
        """
        prompt = build_user_prompt(filename, language, patch)
        try:
            response = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response["message"]["content"]
            logger.debug("Raw model output for %s:\n%s", filename, raw)
            cleaned = _extract_json(raw)
            result = json.loads(cleaned)
            # normalise — ensure required keys exist
            result.setdefault("issues", [])
            result.setdefault("overall_score", 0)
            result.setdefault("summary", "")
            return result
        except json.JSONDecodeError:
            logger.warning("Malformed JSON from model for %s", filename)
            return {"issues": [], "overall_score": 0, "summary": "Parse error"}
        except Exception as exc:
            logger.error("Analysis failed for %s: %s", filename, exc)
            return {"issues": [], "overall_score": 0, "summary": f"Error: {exc}"}
