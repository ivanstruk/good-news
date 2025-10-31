
import os
import random
import pandas as pd
from pathlib import Path
import datetime

from askana.ana import answer_ask_ana

from utils.translator import translate_post_content,load_language_config, _get_lang_code, _get_text
from utils.poster import upload_featured_image, post_to_wordpress
from utils.db_utils import save_generated_article
from utils.logger import logger
from typing import Optional

# Translation Settings
excel_file = Path("blog_config.xlsx")  # adjust if stored elsewhere
supported_languages = load_language_config(excel_file)

# Questions
questions = pd.read_csv("askana/questions.csv")
unanswered = questions[questions["dt_answered"].isna() | (questions["dt_answered"] == "")]
unanswered = unanswered["desc_question"].tolist()
random.shuffle(unanswered)
chosen = unanswered[0]
logger.info("Chosen question: {}".format(chosen))

# Load writer template
template_path = os.path.join(os.path.dirname(__file__), "askana/askana_template.txt")
try:
    with open(template_path, "r", encoding="utf-8") as file:
        template = file.read()
    logger.debug(f"Loaded writer template from {template_path}")
except Exception as e:
    logger.error(f"Failed to load writer template: {e}")
    raise

# Write the response
result = answer_ask_ana(chosen)
if result["status"] == "answered":
    tags = ["Advice", "Ask Ana", "Saveti", "Pitanje"]
    body = result["data"]
    title = "{}?".format(chosen.split("?")[0])
    question_context = "{}?".format(chosen.split("?")[1])
    
    filled_template = template.format(
            question=question_context,
            answer=body
        )

    # Translation
    supported_languages = [lang for lang in supported_languages if lang["run"]]
    translated_articles = []

    for language in supported_languages:
        translated_title, translated_article = translate_post_content(
            title_en=title, 
            body_en=filled_template, 
            lang=language["lang"])

        #We are going to need this variable later.
        translation = {
            "title" : translated_title,
            "body" : translated_article,
            "language" : language["code"]}

        translated_articles.append(translation)

        drafts_dir = Path(__file__).resolve().parent / "drafts/{}".format(language["code"])
        drafts_dir.mkdir(exist_ok=True)  # create folder if it doesn't exist
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        file_path = drafts_dir / f"{timestamp}.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(translated_title + "\n\n")      # Title at the top
            f.write(translated_article + "\n\n")  
            f.write("Tags: " + ", ".join(tags) + "\n\n")

    logger.info(f"Draft saved: {file_path}")

    # Save draft for debugging (English)
    drafts_dir = Path(__file__).resolve().parent / "drafts/EN"
    drafts_dir.mkdir(exist_ok=True)  # create folder if it doesn't exist
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    file_path = drafts_dir / f"{timestamp}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(title + "\n\n")      # Title at the top
        f.write(filled_template + "\n\n")

    logger.info(f"Draft saved: {file_path}")

    # Image Generation (skipping in this case)
    image_id = 334
    
    # === Posting to WordPress (multi-language with Polylang linking) ===
    posted_ids: dict[str, int] = {}   # e.g. {"en": 123, "de": 456, ...}
    
    # 1) Post English base article first (so other languages can link to it)
    topic = "Ask Ana"
    base_response = post_to_wordpress(
        title=title,
        content=filled_template,
        featured_image_id=image_id,
        tags=tags,
        categories=[topic],
        language="en",                # ensure EN is the canonical source
        translations=None,            # nothing to link yet
    )

    if base_response is not None:
        en_id = int(base_response.get("id"))
        posted_ids["en"] = en_id

        dt_published = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_generated_article(
            title=title,
            content=filled_template,
            topic=topic,
            category=topic,
            summary=" ",
            link=base_response.get("link"),
            dt_published=dt_published,
        )

        # Optional: store an EN draft alongside translated drafts for parity
        en_dir = Path(__file__).resolve().parent / "drafts/EN"
        en_dir.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        with open(en_dir / f"{ts}.txt", "w", encoding="utf-8") as f:
            f.write(title + "\n\n")
            f.write(filled_template + "\n\n")

    else:
        logger.error("English base post failed; skipping translations.")
        print("Done")
        raise SystemExit(1)

    # 2) Post each translated article and link it to all previously posted siblings
    for item in translated_articles:
        code = _get_lang_code(item)
        if not code:
            logger.warning("Skipping translation without a valid language code: %s", item)
            continue

        # Pull translated fields with graceful fallbacks
        t_title = _get_text(item, "title", "headline") or title
        t_body = _get_text(item, "content", "body", "text")
        if not t_body:
            logger.warning("Skipping %s translation without content/body.", code)
            continue

        #t_summary = _get_text(item, "summary", "abstract") or summary
        t_tags = item.get("tags", tags) or tags  # reuse EN tags if not provided

        response = post_to_wordpress(
            title=t_title,
            content=t_body,
            featured_image_id=image_id,     # reuse the same featured image
            tags=t_tags,
            categories=[topic],
            language=code,                  # Polylang language slug/code (e.g., "de", "ru", "fr")
            translations=posted_ids,        # link to everything posted so far (incl. EN)
        )

        if response is None:
            logger.error("Failed to post %s translation.", code.upper())
            continue

        # Record this language’s post id (so the next languages can link to it too)
        lang_post_id = int(response.get("id"))
        posted_ids[code] = lang_post_id

        drafts_dir = Path(__file__).resolve().parent / f"drafts/{code.upper()}"
        drafts_dir.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        file_path = drafts_dir / f"{ts}.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(t_title + "\n\n")
            f.write(t_body + "\n\n")
            if isinstance(t_tags, (list, tuple)):
                f.write("Tags: " + ", ".join(map(str, t_tags)) + "\n\n")
            else:
                f.write("Tags: " + str(t_tags) + "\n\n")

    print("Done")
else:
    # already_answered | flagged_skip | error
    logger.info(f"{result['status']}: {result['data']}")