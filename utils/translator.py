from __future__ import annotations
from utils.logger  import logger
from pathlib import Path
from typing import Literal, Optional
from openai import OpenAI

DEFAULT_MODEL = "gpt-4o-mini"

# Prompts live in: <repo-root>/prompts/*.txt
# This module is in: <repo-root>/utils/translator.py
PROMPTS_DIR = (Path(__file__).resolve().parent.parent / "prompts").resolve()

# Map logical “kinds” to prompt file names inside /prompts
PROMPT_FILES: dict[str, str] = {
    "title": "title_translation_system.txt",
    "article": "article_translation_system.txt",
}


def _load_system_prompt(kind: Literal["title", "article"]) -> str:
    """
    Load the system prompt for the given kind from the prompts directory.

    The expected files (customize as you like) are:
      - prompts/title_translation_system.txt
      - prompts/article_translation_system.txt
    """
    file_name = PROMPT_FILES.get(kind)
    if not file_name:
        raise ValueError(f"Unsupported prompt kind: {kind!r}")

    prompt_path = PROMPTS_DIR / file_name
    try:
        content = prompt_path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"System prompt file is empty: {prompt_path}")
        logger.info("Loaded system prompt '%s' from %s", kind, prompt_path)
        return content
    except FileNotFoundError as exc:
        msg = (
            f"System prompt file not found for kind '{kind}': {prompt_path}.\n"
            f"Create it with your desired instructions."
        )
        logger.error(msg)
        raise FileNotFoundError(msg) from exc

def translate_text(
    text: str,
    target_language: str,
    *,
    kind: Literal["title", "article"] = "article",
    system_prompt_override: Optional[str] = None,
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Translate *English* text into `target_language` using the OpenAI API.

    Args:
        text: The English source text to translate.
        target_language: The target language (e.g., "Serbian", "French").
        kind: Which built-in system prompt to use ("title" or "article").
              This selects a file in the root-level `prompts/` folder.
        system_prompt_override: If provided, use this string instead of loading
              from a file. Useful for one-off/custom behaviors.
        model: OpenAI model name. Defaults to a fast, inexpensive model.

    Returns:
        The translated text as a plain string.

    Raises:
        FileNotFoundError: If the required system prompt file is missing.
        RuntimeError: For API or unexpected errors.
        ValueError: If parameters are invalid.
    """
    if not text:
        logger.warning("translate_text called with empty text.")
        return ""

    # Resolve the system prompt: override > file-based
    if system_prompt_override is not None:
        system_prompt = system_prompt_override.strip()
        logger.info("Using system_prompt_override for kind '%s'.", kind)
    else:
        system_prompt = _load_system_prompt(kind)

    client = OpenAI()

    # We instruct the model clearly about direction (always English -> target)
    user_prompt = (
        f"Translate the following text from English to {target_language}.\n\n"
        f"{text}"
    )

    try:
        logger.info(
            "Translating (%s) to %s with model %s. Input chars=%d",
            kind,
            target_language,
            model,
            len(text),
        )

        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        translated = (response.output_text or "").strip()
        if not translated:
            raise RuntimeError("OpenAI returned an empty translation.")
        logger.debug(
            "Translation success (%s): %.60r ...", kind, translated[:60]
        )
        return translated

    except Exception as exc:  # Broad catch to rewrap with context + logging
        logger.exception("Translation failed (%s -> %s): %s", kind, target_language, exc)
        raise RuntimeError(f"Translation failed: {exc}") from exc


def translate_post_content(title_en: str, body_en: str, lang: str) -> tuple[str, str]:
    """
    Translate both title and body of an article from English to the given language.
    Returns (translated_title, translated_body).
    """
    title_translated = translate_text(title_en, target_language=lang, kind="title")
    body_translated = translate_text(body_en, target_language=lang, kind="article")
    return title_translated, body_translated


