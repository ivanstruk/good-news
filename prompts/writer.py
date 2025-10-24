from utils.logger import logger
import os
import unicodedata
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import re
from typing import Optional, List, Tuple


# === Setup ===
base_dir = Path(__file__).resolve().parent.parent
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# OpenAI client
openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    logger.error("OPENAI_API_KEY is not set in the environment.")

client = OpenAI(api_key=openai_key)


# === Helpers ===
def clean_text(text: str) -> str:
    """
    Normalize Unicode and replace non-breaking spaces with regular spaces.
    """
    return unicodedata.normalize("NFKC", text).replace("\u00A0", " ").strip()


# === Main Functions ===
def write_article(research: str, post_history: Optional[str]):
    """
    Fill the article-writing template with research and past history,
    save the filled prompt, and call OpenAI to generate the article.

    Returns:
        tuple[str, str]: (generated_article, saved_prompt_path)
    """
    logger.info("Starting article generation...")

    # Load writer template
    template_path = os.path.join(os.path.dirname(__file__), "writer_template.txt")
    try:
        with open(template_path, "r", encoding="utf-8") as file:
            template = file.read()
        logger.debug(f"Loaded writer template from {template_path}")
    except Exception as e:
        logger.error(f"Failed to load writer template: {e}")
        raise

    if post_history is None:
        filled_prompt = template.format(
            articles=research,
            post_header="",
            post_history=""
        )
        logger.debug("Filled prompt without post history.")
    else:
        post_header = "=== PAST ARTICLES (SUMMARIES) ==="
        filled_prompt = template.format(
            articles=research,
            post_header=post_header,
            post_history=post_history
        )
        logger.debug("Filled prompt with post history.")

    # Clean prompt text
    try:
        filled_prompt = clean_text(filled_prompt)
    except Exception as e:
        logger.warning(f"Failed to clean filled prompt: {e}")

    # Save filled prompt for logging
    save_dir = os.path.join(os.path.dirname(__file__), "logged_prompts")
    os.makedirs(save_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"article_prompt_{timestamp}.txt"
    file_path = os.path.join(save_dir, filename)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(filled_prompt)
        logger.info(f"Saved filled prompt to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save filled prompt: {e}")
        raise

    # Load system prompt
    system_prompt_path = os.path.join(os.path.dirname(__file__), "writer_system_prompt.txt")
    try:
        with open(system_prompt_path, "r", encoding="utf-8") as file:
            system_prompt = file.read()
        logger.debug(f"Loaded system prompt from {system_prompt_path}")
    except Exception as e:
        logger.error(f"Failed to load system prompt: {e}")
        raise

    # Call OpenAI
    logger.info("Requesting article from OpenAI API...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": filled_prompt}
            ],
            temperature=0.4,
            max_tokens=4096
        )
        logger.info("Article generated successfully.")
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        raise

    article = response.choices[0].message.content
    return article, file_path

def generate_article_title(article_text: str) -> str:
    logger.info("Generating article title...")
    system_prompt = (
        "You are an expert news editor. "
        "Your job is to create concise, engaging, and unique titles for news articles. "
        "The title should:\n"
        "- Be under 12 words\n"
        "- Avoid clickbait\n"
        "- Capture the main story accurately"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Here is the article (~1000 words):\n\n{article_text}"}
            ],
            temperature=0.7,
            max_tokens=100
        )
        logger.info("Article title generated successfully.")
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API call failed while generating title: {e}")
        raise


def clean_tag(tag: str) -> str:
    """Convert a tag into a clean SEO slug."""
    # Lowercase, strip whitespace
    tag = tag.strip().lower()
    # Replace any non-alphanumeric sequence with a single hyphen
    tag = re.sub(r"[^a-z0-9]+", "-", tag)
    # Collapse multiple hyphens and trim ends
    tag = re.sub(r"-{2,}", "-", tag).strip("-")
    return tag

def summarize_article(article_text: str) -> Tuple[str, List[str]]:
    """
    Summarizes a news article and extracts clean, SEO-friendly tags.
    Returns: (summary, tags)
    """
    logger.info("Summarizing article and generating tags...")

    system_prompt = (
        "You are an expert news editor. "
        "Summarize long news articles into one clear, objective paragraph. "
        "Also, generate 5–10 relevant blog tags (short keywords, not sentences). "
        "Return them clearly after 'Tags:' on new lines or comma-separated."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Summarize this article and create tags:\n\n{article_text}"}
            ],
            temperature=0.5,
            max_tokens=400
        )
        output = response.choices[0].message.content.strip()
        logger.info("Summary and tags generated successfully.")
    except Exception as e:
        logger.error(f"OpenAI API call failed while summarizing article: {e}")
        raise

    # --- Parse response ---
    summary, tags = "", []

    if "Tags:" in output:
        parts = output.split("Tags:", 1)
        summary = parts[0].replace("Summary:", "").strip()
        tags_text = parts[1].strip()

        # Split tags by commas or newlines
        raw_tags = re.split(r"[,|\n]+", tags_text)
        raw_tags = [t.strip() for t in raw_tags if t.strip()]

        # Clean up tags and remove duplicates
        seen = set()
        tags = []
        for t in raw_tags:
            clean = clean_tag(t)
            if clean and clean not in seen:
                seen.add(clean)
                tags.append(clean)

    else:
        summary = output.strip()

    return summary, tags
