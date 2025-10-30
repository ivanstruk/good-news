from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI
from utils.logger import logger  # your project logger


# =========================
# Environment & Path Setup
# =========================
# project root is the parent of askana/
BASE_DIR: Path = Path(__file__).resolve().parent.parent
DOTENV_PATH = BASE_DIR / ".env"
load_dotenv(DOTENV_PATH.as_posix())

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set in the environment.")

# Single, shared OpenAI client (can be overridden in answer_ask_ana)
client = OpenAI(api_key=OPENAI_API_KEY)


# =========================
# Configuration
# =========================
@dataclass(frozen=True)
class AnaConfig:
    """
    Ask Ana configuration. All paths are anchored to BASE_DIR
    to keep behavior consistent with the rest of the project.
    """
    rel_prompts_dir: Path = Path("askana")  # relative to BASE_DIR
    system_prompt_file: str = "system_prompt.txt"
    user_prompt_file: str = "user_prompt.txt"
    csv_filename: str = "questions.csv"
    model: str = "gpt-4.1-mini"

    @property
    def prompts_dir(self) -> Path:
        return BASE_DIR / self.rel_prompts_dir

    @property
    def system_prompt_path(self) -> Path:
        return self.prompts_dir / self.system_prompt_file

    @property
    def user_prompt_path(self) -> Path:
        return self.prompts_dir / self.user_prompt_file

    @property
    def csv_path(self) -> Path:
        return self.prompts_dir / self.csv_filename


# =========================
# Helpers
# =========================
def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace for stable comparisons."""
    return " ".join(text.strip().lower().split())


def _truthy(value: Optional[str]) -> bool:
    """Interpret CSV bool-ish values."""
    if value is None:
        return False
    v = value.strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def _ensure_csv_exists(csv_path: Path) -> None:
    """Create CSV with headers if it doesn't exist."""
    if not csv_path.exists():
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["desc_question", "bool_flag", "dt_answered"])
        logger.info("Created questions.csv at %s", csv_path)


def _read_rows(csv_path: Path) -> List[Dict[str, str]]:
    """Read all rows as dicts and validate headers (BOM-tolerant)."""
    # NOTE: utf-8-sig removes a leading BOM if present
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        expected = ["desc_question", "bool_flag", "dt_answered"]
        # Normalize any stray BOMs on the first fieldname (extra defense)
        fieldnames = [fn.lstrip("\ufeff") if isinstance(fn, str) else fn for fn in (reader.fieldnames or [])]
        if fieldnames != expected:
            raise ValueError(
                f"CSV at {csv_path} must have headers exactly: {', '.join(expected)} "
                f"(found {fieldnames})"
            )
        return list(reader)


def _write_rows(csv_path: Path, rows: List[Dict[str, str]]) -> None:
    """Write rows back to CSV deterministically."""
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["desc_question", "bool_flag", "dt_answered"]
        )
        writer.writeheader()
        writer.writerows(rows)


def _find_row_index(rows: List[Dict[str, str]], question: str) -> Optional[int]:
    """Find row index by normalized question match."""
    target = _normalize(question)
    for idx, row in enumerate(rows):
        if _normalize(row.get("desc_question", "")) == target:
            return idx
    return None


def _load_prompts(cfg: AnaConfig) -> tuple[str, str]:
    """Load system/user prompt text files, strict and explicit."""
    if not cfg.system_prompt_path.exists():
        raise FileNotFoundError(f"Missing system prompt: {cfg.system_prompt_path}")
    if not cfg.user_prompt_path.exists():
        raise FileNotFoundError(f"Missing user prompt: {cfg.user_prompt_path}")

    system_prompt = cfg.system_prompt_path.read_text(encoding="utf-8").strip()
    user_prompt = cfg.user_prompt_path.read_text(encoding="utf-8").strip()

    if not system_prompt:
        raise ValueError("System prompt file is empty.")
    if not user_prompt:
        raise ValueError("User prompt file is empty.")

    return system_prompt, user_prompt


def _now_iso() -> str:
    """UTC ISO8601 without microseconds for neat auditing."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# =========================
# Public API
# =========================
def answer_ask_ana(
    question: str,
    *,
    config: Optional[AnaConfig] = None,
    client_override: Optional[OpenAI] = None,
    model: Optional[str] = None,
) -> Dict[str, str]:
    """
    Answer a reader's question in Ana's style.

    Decision logic:
      • If the question exists and dt_answered is set → skip (already_answered)
      • If the question exists and dt_answered empty and bool_flag empty/false → answer
      • If the question is NEW → add it and answer
      • If bool_flag is truthy → skip (flagged)

    Returns:
      {
        "status": "answered" | "already_answered" | "flagged_skip" | "error",
        "data":   "<answer text or reason>"
      }
    """
    if not question or not question.strip():
        return {"status": "error", "data": "Question is empty."}

    cfg = config or AnaConfig()
    model_name = model or cfg.model

    # Ensure CSV exists
    _ensure_csv_exists(cfg.csv_path)

    # Load rows and locate question
    rows = _read_rows(cfg.csv_path)
    row_idx = _find_row_index(rows, question)

    if row_idx is None:
        # New question → append and proceed to answer
        rows.append(
            {"desc_question": question.strip(), "bool_flag": "", "dt_answered": ""}
        )
        row_idx = len(rows) - 1
        logger.info("New question appended to CSV at index %d.", row_idx)
    else:
        logger.info("Question present in CSV at index %d.", row_idx)

    row = rows[row_idx]

    # Respect flags and already-answered states
    if row.get("dt_answered", "").strip():
        logger.info("Question already answered. Skipping.")
        return {"status": "already_answered", "data": "Already answered."}

    if _truthy(row.get("bool_flag", "")):
        logger.info("Question flagged for manual review. Skipping.")
        return {"status": "flagged_skip", "data": "Flagged for manual review."}

    # Build prompts
    system_prompt, user_prompt_template = _load_prompts(cfg)
    try:
        user_prompt = user_prompt_template.format(question=question.strip())
    except KeyError:
        # If braces used for something else, append cleanly.
        user_prompt = f"{user_prompt_template}\n\nQuestion:\n{question.strip()}"

    # OpenAI client
    api = client_override or client
    if api is None:
        logger.error("OpenAI client not available.")
        return {"status": "error", "data": "OpenAI client not available."}

    logger.info("Requesting completion from model: %s", model_name)
    try:
        completion = api.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        answer_text = (completion.choices[0].message.content or "").strip()
        if not answer_text:
            raise RuntimeError("Empty completion content.")
    except Exception as exc:
        logger.error("OpenAI API error: %s", exc)
        return {"status": "error", "data": f"OpenAI API error: {exc}"}

    # Persist timestamp
    rows[row_idx]["dt_answered"] = _now_iso()
    _write_rows(cfg.csv_path, rows)
    logger.info("Answer recorded at %s", rows[row_idx]["dt_answered"])

    return {"status": "answered", "data": answer_text}


# =========================
# CLI (Optional)
# =========================
if __name__ == "__main__":
    import sys

    # Keep your console style for quick manual testing
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] ana: %(message)s",
    )

    if len(sys.argv) < 2:
        print('Usage: python -m askana.ana "Your question here"')
        sys.exit(1)

    q = sys.argv[1]
    res = answer_ask_ana(q)
    print(res["status"])
    print("-" * 80)
    print(res["data"])
