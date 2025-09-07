import os
import unicodedata
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI


# === Setup ===
base_dir = Path(__file__).resolve().parent.parent
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# OpenAI client
openai_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_key)


# === Helpers ===
def clean_text(text: str) -> str:
    """
    Normalize Unicode and replace non-breaking spaces with regular spaces.
    """
    return unicodedata.normalize("NFKC", text).replace("\u00A0", " ").strip()


# === Main Functions ===
def write_article(research: str, post_history: str | None):
    """
    Fill the article-writing template with research and past history,
    save the filled prompt, and call OpenAI to generate the article.

    Args:
        research (str): Formatted research content.
        post_history (str | None): Summaries of past articles, or None.

    Returns:
        tuple[str, str]: (generated_article, saved_prompt_path)
    """
    # Load writer template
    template_path = os.path.join(os.path.dirname(__file__), "writer_template.txt")
    with open(template_path, "r", encoding="utf-8") as file:
        template = file.read()

    if post_history is None:
        filled_prompt = template.format(
            articles=research,
            post_header="",
            post_history=""
        )
    else:
        post_header = "=== PAST ARTICLES (SUMMARIES) ==="
        filled_prompt = template.format(
            articles=research,
            post_header=post_header,
            post_history=post_history
        )

    # Clean prompt text
    try:
        filled_prompt = clean_text(filled_prompt)
    except Exception:
        pass

    # Save filled prompt for logging
    save_dir = os.path.join(os.path.dirname(__file__), "logged_prompts")
    os.makedirs(save_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"article_prompt_{timestamp}.txt"
    file_path = os.path.join(save_dir, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(filled_prompt)

    # Load system prompt
    system_prompt_path = os.path.join(os.path.dirname(__file__), "writer_system_prompt.txt")
    with open(system_prompt_path, "r", encoding="utf-8") as file:
        system_prompt = file.read()

    # Call OpenAI
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": filled_prompt}
        ],
        temperature=0.4,
        max_tokens=4096
    )

    article = response.choices[0].message.content
    return article, file_path


def generate_article_title(article_text: str) -> str:
    """
    Generate a unique, concise, and engaging article title.

    Args:
        article_text (str): Full article text.

    Returns:
        str: Generated article title.
    """
    system_prompt = (
        "You are an expert news editor. "
        "Your job is to create concise, engaging, and unique titles for news articles. "
        "The title should:\n"
        "- Be under 12 words\n"
        "- Avoid clickbait\n"
        "- Capture the main story accurately"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the article (~1000 words):\n\n{article_text}"}
        ],
        temperature=0.7,
        max_tokens=100
    )

    return response.choices[0].message.content.strip()


def summarize_article(article_text: str):
    """
    Summarize an article into one concise paragraph
    and generate SEO/blog tags.

    Args:
        article_text (str): Full article text (700–1000 words).

    Returns:
        tuple[str, list[str]]: (summary, tags)
    """
    system_prompt = (
        "You are an expert news editor. "
        "Summarize long news articles into one clear, objective paragraph. "
        "Also, generate 5–10 relevant blog tags (as short keywords, not sentences). "
        "Tags should be SEO-friendly and capture the article's core topics."
    )

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

    # Parse response (expecting "Summary: ...\nTags: ...")
    summary, tags = "", []
    if "Tags:" in output:
        parts = output.split("Tags:")
        summary = parts[0].replace("Summary:", "").strip()
        tags_text = parts[1].strip()
        tags = [t.strip() for t in tags_text.replace(",", "\n").split("\n") if t.strip()]
    else:
        summary = output

    return summary, tags
