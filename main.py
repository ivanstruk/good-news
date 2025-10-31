import pandas as pd
from pathlib import Path
import datetime

from utils.logger import logger
from utils.scraper import research, scrapeRSS, fetchNews
from utils.telegram_scraper import fetchTelegram
from utils.poster import upload_featured_image, post_to_wordpress
from utils.db_utils import DB_PATH, backup_sqlite, connect, save_generated_article
from utils.editor import refine_article
from utils.image import process_image
from utils.translator import translate_post_content, load_language_config, _get_lang_code, _get_text

from prompts.prompter import build_news_prompt, build_history_prompt
from prompts.writer import write_article, summarize_article, generate_article_title

from typing import Optional

logger.info("Modules imported.")

backup_path: Path = DB_PATH.with_name("backup_articles.db")
backup_sqlite(DB_PATH, backup_path)
logger.info(f"Startup backup OK → {backup_path}")


# Weekly Schedule
schedule_sheet = pd.read_excel(
    "blog_config.xlsx",
    sheet_name="weekly_scheduler",
    skiprows=3,     # Skip rows above row 4
    usecols="B:H",  # Read only columns B through H
    nrows=10        # Read 10 rows (B4:H13)
)
schedule = [
    {"Weekday": col, "Topics": schedule_sheet[col].dropna().tolist()}
    for col in schedule_sheet.columns
]

weekday = datetime.datetime.today().strftime("%A")
topic_agenda = schedule_sheet[weekday].dropna().tolist() #defines the topics relevant to current weekday

logger.info("Schedule determined. Today is {}".format(weekday))

# Topics
sources = pd.read_excel("blog_config.xlsx", sheet_name="sources").to_dict(orient='records')
sources = [s for s in sources if s["bool_visibility"]==True]

# Translation Settings
excel_file = Path("blog_config.xlsx")  # adjust if stored elsewhere
supported_languages = load_language_config(excel_file)


# Initializing script...
for topic in topic_agenda:
    logger.info("Topic pool, topic: {}".format(topic))
    
    # === Research and News Curration ===
    temp_research_db = []
    filtered_sources = [s for s in sources if s["desc_topic_primary"]==topic]
    for source in filtered_sources:
        channel = source["desc_channel"]

        if channel == "SERP":
            SERP_articles = research(source["desc_payload"], source["desc_topic_primary"], source["limit"])
            if len(SERP_articles) > 0:
                temp_research_db.extend(SERP_articles)

        elif channel == "RSS":
            RSS_articles = scrapeRSS(source["desc_payload"], source["desc_topic_primary"], source["limit"])
            if len(RSS_articles) > 0:
                temp_research_db.extend(RSS_articles)

        elif channel == "News":
            news_articles = fetchNews(source)
            if len(news_articles) > 0:
                temp_research_db.extend(news_articles)
        
        elif channel == "Telegram":
            telegram_messages = fetchNews(source)
            if len(telegram_messages) > 0:
                temp_research_db.extend(telegram_messages)

        else:
            logger.info("Channel unrecognized: {}".format(channel))
            pass
    
    # === Article Generation ===
    news = build_news_prompt(temp_research_db, 10000)
    past_works = build_history_prompt(topic, limit=10)

    article_text, article_prompt = write_article(news,past_works)
    summary, tags = summarize_article(article_text)
    title = generate_article_title(article_text)

    # === Editor ===
    article_text = refine_article(article_text, limit=5, threshold=40)
    
    # === Translation ===
    supported_languages = [lang for lang in supported_languages if lang["run"]]
    translated_articles = []

    for language in supported_languages:
        translated_title, translated_article = translate_post_content(
            title_en=title, 
            body_en=article_text, 
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

    # === Save draft for debugging (English) ===
    drafts_dir = Path(__file__).resolve().parent / "drafts/EN"
    drafts_dir.mkdir(exist_ok=True)  # create folder if it doesn't exist
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    file_path = drafts_dir / f"{timestamp}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(title + "\n\n")      # Title at the top
        f.write(article_text + "\n\n")  
        f.write("Tags: " + ", ".join(tags) + "\n\n")
        f.write("Summary:\n" + summary + "\n")

    logger.info(f"Draft saved: {file_path}")

    # === Image Generation ===
    d = pd.read_excel("blog_config.xlsx", sheet_name="image_prompts").to_dict(orient='records')
    image_prompt = next(
        (item["desc_image_prompt"] for item in d if item["desc_topic_primary"] == topic),
        next((item["desc_image_prompt"] for item in d if item["desc_topic_primary"] == "General"), None)
    )
    featured_image = process_image(
        article_summary=summary,
        system_prompt=image_prompt)

    image_id = None
    if featured_image == True:
        image_id = upload_featured_image("assets/featured_image.jpg")

    # === Posting to WordPress (multi-language with Polylang linking) ===

    def _get_lang_code(item: dict) -> Optional[str]:
        """Return a normalized 2–5 char language code from a translation item."""
        for key in ("language", "code", "lang", "slug"):
            if key in item and item[key]:
                code = str(item[key]).strip().lower()
                if 2 <= len(code) <= 5:
                    return code
        return None

    def _get_text(item: dict, *keys: str) -> Optional[str]:
        """Return the first present non-empty string for given keys from item."""
        for k in keys:
            if k in item and isinstance(item[k], str) and item[k].strip():
                return item[k]
        return None

    posted_ids: dict[str, int] = {}   # e.g. {"en": 123, "de": 456, ...}
    
    # 1) Post English base article first (so other languages can link to it)
    base_response = post_to_wordpress(
        title=title,
        content=article_text,
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
            content=article_text,
            topic=topic,
            category=topic,
            summary=summary,
            link=base_response.get("link"),
            dt_published=dt_published,
        )

        # Optional: store an EN draft alongside translated drafts for parity
        en_dir = Path(__file__).resolve().parent / "drafts/EN"
        en_dir.mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        with open(en_dir / f"{ts}.txt", "w", encoding="utf-8") as f:
            f.write(title + "\n\n")
            f.write(article_text + "\n\n")
            f.write("Tags: " + ", ".join(tags) + "\n\n")
            f.write("Summary:\n" + summary + "\n")

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

        # Save per-language DB entry and an on-disk draft
        # dt_published = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # save_generated_article(
        #     title=t_title,
        #     content=t_body,
        #     topic=topic,
        #     category=topic,
        #     summary=t_summary,
        #     link=response.get("link"),
        #     dt_published=dt_published,
        # )

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
