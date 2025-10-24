import os
from pathlib import Path
import re
from typing import Optional
from dotenv import load_dotenv
from openai import OpenAI
from utils.logger import logger

# =========================
# Environment & OpenAI init
# =========================

base_dir = Path(__file__).resolve().parent.parent  # project root
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    logger.error("OPENAI_API_KEY is not set in the environment.")
client = OpenAI(api_key=openai_key)



# ====================================
# 0) Cheap deterministic pre-processing
# ====================================
CLICHE_PATTERNS = (
    r"\bin a dramatic escalation\b",
    r"\bthe stakes are high\b",
    r"\bas the international community watches\b",
    r"\bposes a significant threat to (?:regional|global) stability\b",
    r"\bthe situation remains precarious\b",
    r"\bin response to\b",
    r"\bhas called for\b",
)

def scrub_boilerplate(text: str) -> str:
    """Remove common boilerplate/clichés and tidy whitespace."""
    cleaned = text
    for pat in CLICHE_PATTERNS:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
    # Tighten stacked hedges like "however, nevertheless"
    cleaned = re.sub(
        r"\b(however|nevertheless|nonetheless)\s*,\s*(however|nevertheless|nonetheless)\b",
        r"\1,",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Normalize spaces
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# ===============================================
# 0.5) One-time: de-template the lede (first sent)
# ===============================================
def detemplate_lede_once(text: str) -> str:
    """
    Rewrite ONLY the first sentence to remove generic framing and clichés.
    Keep facts and length; return the full paragraph text.
    """
    system_prompt = (
        "You are a news editor. Rewrite ONLY the first sentence to remove generic framing, "
        "clichés, and overly broad setup. Keep all facts; be concrete and concise. "
        "Return the full paragraph with the revised first sentence. Do not touch later paragraphs."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text.strip()},
    ]
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.4,
        max_tokens=600,
    )
    return resp.choices[0].message.content.strip()

# =========================================
# 1) Unbiased rubric-based grader (no anchor)
# =========================================

def grade_base(article_text: str) -> int:
    """
    Fresh score (1–100) for AI-likeness using a weighted rubric.
    Deterministic: no anchoring; normalized for news conventions.
    """
    system_prompt = (
        "You are an expert news editor and AI content analyst. "
        "Evaluate how much the given article sounds AI-generated (not factual accuracy). "
        "Normalize for length, domain conventions, and AP style; ignore political stance. "
        "Score with this weighted rubric (0–100 each, then weighted average): "
        "1) Template/Formulaic Structure (25%), "
        "2) Generic Filler/Boilerplate (20%), "
        "3) Repetition & Redundancy (15%), "
        "4) Hedging/Balance Tics (15%), "
        "5) Tone Flatness & Lack of Specificity (15%), "
        "6) Mechanical Polish Artifacts (10%). "
        "Anchors: 10=clearly human, 30=mostly human, 50=mixed, 70=likely AI, 90=overt AI template. "
        "Output only one integer 1–100; higher = more AI-like."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": "Article text:\n"
                       f"{article_text.strip()}\n\n"
                       "Return only the integer score.",
        },
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0,
        top_p=0,
        max_tokens=5,
    )

    content = response.choices[0].message.content.strip()
    try:
        score = int("".join(ch for ch in content if ch.isdigit()))
        return max(1, min(score, 100))
    except ValueError:
        raise ValueError(f"Unexpected grading output: {content}")


# ===========================================
# 2) Score smoother (less sticky, but stable)
# ===========================================
def smooth_score(
    previous: Optional[int],
    base: int,
    momentum: float = 0.6,   # less sticky than 0.7
    deadband: int = 1,       # respond to small real changes
    max_step: int = 12       # allow larger per-iteration movement
) -> int:
    """
    Exponential smoothing toward `base` with guards.
    - deadband: ignore tiny changes (<= deadband)
    - momentum: how much to keep from previous (0..1)
    - max_step: cap per-iteration movement
    """
    if previous is None:
        return base

    delta = base - previous
    if abs(delta) <= deadband:
        return previous

    target = previous * momentum + base * (1.0 - momentum)
    step = int(round(target - previous))
    if step > 0:
        step = min(step, max_step)
    elif step < 0:
        step = max(step, -max_step)
    return max(1, min(100, previous + step))


# ==================================
# 3) Rewriter aligned to the rubric
# ==================================
def humanize_article(article_text: str, score: Optional[int] = None, mode: str = "gentle") -> str:
    """
    Refine the article to read as if written by a human journalist.

    mode:
      - "gentle": small, precise edits (default)
      - "aggressive": stronger de-templating when stuck
    """
    # Shared base instructions
    core_prompt = (
        "You are a professional human news editor. "
        "Refine the article so it reads as if written by a real journalist, without changing facts. "
        "Target the following (do not fabricate info): "
        "1) Remove template/framing clichés and boilerplate. "
        "2) Reduce hedging/balance tics unless sourced and necessary. "
        "3) Cut repetition; merge duplicate ideas; vary sentence rhythm (include some short sentences). "
        "4) Prefer concrete, specific language over abstractions; keep quotes and named entities intact. "
        "5) Keep structure and length similar; do NOT summarize or shorten."
    )

    if mode == "gentle":
        style_tail = (
            "Make subtle, precise edits only where needed. Preserve tone and paragraph structure. "
            "Avoid sweeping rewrites."
        )
        temperature = 0.6
        presence_penalty = 0.25
        frequency_penalty = 0.3
    else:  # aggressive
        style_tail = (
            "Apply stronger de-templating: rewrite generic openings, replace vague transitions with concrete ones "
            "(without adding facts), break up monotonous long sentences, and reduce stock phrasing aggressively. "
            "Keep all factual content intact and do not shorten overall length."
        )
        temperature = 0.75
        presence_penalty = 0.4
        frequency_penalty = 0.45

    system_prompt = f"{core_prompt} {style_tail}"

    if score is not None:
        user_message = (
            f"Current AI-likeness score: {score}. "
            "Edit to reduce AI-like tone per the targets above, keeping meaning intact.\n\n"
            f"Article text:\n{article_text.strip()}"
        )
    else:
        user_message = (
            "Edit to reduce AI-like tone per the targets above, keeping meaning intact.\n\n"
            f"Article text:\n{article_text.strip()}"
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=temperature,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
    )
    return response.choices[0].message.content.strip()


# ====================
# 4) Main refinement
# ====================

def refine_article(
    article_text: str,
    limit: int = 5,
    threshold: int = 20,
    require_base_improvement: int = 2,   # was 3
    no_gain_patience: int = 3            # was 2
) -> str:
    """
    Iteratively rewrite an article until it sounds less AI-like.
    Returns the best (lowest-smoothed-score) version if threshold not reached.
    """
    # One-time deterministic scrub
    test_article = scrub_boilerplate(article_text)

    # Optional: one-time de-templating of the first sentence
    try:
        test_article = detemplate_lede_once(test_article)
        logger.info("Applied one-time lede de-templating pass.")
    except Exception as exc:  # keep going if this fails
        logger.info(f"Skipping lede de-templating due to error: {exc}")

    counter = 0
    prev_smoothed: Optional[int] = None

    # tracking best-so-far (by smoothed score)
    best_score = 101
    best_article = test_article
    best_iter = 0

    # base-score improvement tracker
    no_gain_streak = 0
    prev_base: Optional[int] = None

    while counter < limit:
        counter += 1
        logger.info(f"Iteration {counter}")

        # 1) Grade
        base = grade_base(test_article)
        my_grade = smooth_score(prev_smoothed, base, momentum=0.6, deadband=1, max_step=12)
        prev_smoothed = my_grade
        logger.info(f"Base score: {base} | Smoothed score: {my_grade}")

        # 2) Track best
        if my_grade < best_score:
            best_score = my_grade
            best_article = test_article
            best_iter = counter
            logger.info(f"New best iteration: {counter} (score {my_grade})")

        # 3) Stop if good enough
        if my_grade <= threshold:
            logger.info("✅ We have a human article!")
            return test_article

        # 4) Base-improvement tracking
        if prev_base is not None and (prev_base - base) < require_base_improvement:
            no_gain_streak += 1
        else:
            no_gain_streak = 0
        prev_base = base

        # 5) If we're about to hit patience limit, do one aggressive pass
        if no_gain_streak == no_gain_patience - 1 and counter < limit:
            logger.info("Stagnation detected — applying one aggressive de-templating pass...")
            test_article = humanize_article(test_article, score=base, mode="aggressive")
            continue

        # 6) Early stop if still no progress
        if no_gain_streak >= no_gain_patience:
            logger.info("No meaningful base-score improvement for consecutive rounds. Stopping early.")
            logger.info(f"Returning best-so-far from iteration {best_iter} (score {best_score}).")
            return best_article

        # 7) Otherwise continue with gentle edits
        logger.info("Rewriting to sound more human...")
        test_article = humanize_article(test_article, score=base, mode="gentle")

    logger.info("⚠️ Reached iteration limit without crossing threshold.")
    logger.info(f"Returning best-so-far from iteration {best_iter} (score {best_score}).")
    return best_article
