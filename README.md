# good-news

⚠️ **Work in Progress**: This project is under active development. Expect breaking changes and incomplete features.


Automated, prompt-driven news generation and publishing pipeline for WordPress.

This project ingests topics and sources from an Excel workbook, gathers fresh inputs via RSS, Google News (SerpAPI), and Telegram channels, then uses the OpenAI API to draft articles, summarize them, and publish to a WordPress site — all on an adjustable weekly schedule.

---

## ✨ Features

- **Topic- & schedule-driven**: Uses `blog_config.xlsx` to decide *what* to post and *when* (per weekday).
- **Multi-source research**:
  - **RSS** via `feedparser`
  - **Google News** via **SerpAPI**
  - **Telegram** via `Telethon`
- **Content generation** with OpenAI (configurable prompts, style, and sentiment).
- **Post-processing**: auto title, summary, and tags generation.
- **WordPress publishing** (REST API), including optional featured image upload.
- **SQLite** persistence, duplicate protection, and simple history retrieval to avoid repetition.
- **Structured logging** to `logs/operations.log`.

---

## 🗂️ Repository layout

```
good-news/
├─ main.py                    # Orchestrates daily run: read schedule → gather sources → generate → post
├─ blog_config.xlsx           # Scheduler (weekly) + source registry + blocked domains
├─ articles.db                # SQLite database (created automatically if missing)
├─ prompts/
│  ├─ prompter.py             # Builds the news/history prompts from research + past posts
│  ├─ writer.py               # OpenAI calls for article writing and summarization
│  ├─ writer_system_prompt.txt
│  ├─ writer_template.txt
│  ├─ article_template.txt
│  ├─ past_article_template.txt
│  └─ logged_prompts/         # Saved, filled prompts for traceability
├─ utils/
│  ├─ scraper.py              # RSS + SerpAPI + generic page parse + (optional) News site parsing
│  ├─ telegram_scraper.py     # Telegram channel fetch via Telethon
│  ├─ db_utils.py             # Insert/fetch utilities around SQLite (posted_articles etc.)
│  ├─ poster.py               # WordPress REST API helpers (media upload, post create)
│  └─ logger.py               # Shared logger setup → logs/operations.log
├─ logs/
│  └─ operations.log
├─ requirements.txt
├─ .env_sample                # Example environment variables
└─ .env                       # Your local secrets (not committed)
```

> **Note:** The WordPress helper (`utils/poster.py`) expects standard WP REST API credentials (see **Configuration** below).

---

## 🧱 Architecture (high level)

```
                 ┌──────────────────┐         ┌──────────────────────────┐
                 │  blog_config.xlsx│         │   blocked_domains sheet  │
                 └─────────┬────────┘         └────────────┬─────────────┘
                           │                                │
                  (weekday: topics)                  (filter source URLs)
                           │                                │
                           ▼                                ▼
                    ┌────────────┐       ┌───────────────────────────────┐
   Sources ═══════> │ utils/*    │       │ Research DB (in memory)       │
   (RSS/Serp/Tele)  │ scraper.py │──────▶│  title, text, source, link... │
                    │ telegram_* │       └────────────────┬──────────────┘
                    └─────┬──────┘                        │
                          │                                │
                          ▼                                ▼
                    ┌───────────────────┐         ┌─────────────────────────┐
                    │ prompts/prompter  │         │ prompts/writer (OpenAI) │
                    │ build_*_prompt    │────────▶│ write_article + summary │
                    └─────────┬─────────┘         └────────────┬────────────┘
                              │                                │
                              ▼                                ▼
                        ┌────────────┐                  ┌──────────────┐
                        │  SQLite    │◀─────────────────│  db_utils    │
                        │ articles.db│    (dedupe, log) │ insert/fetch │
                        └─────┬──────┘                  └──────┬───────┘
                              │                                │
                              ▼                                ▼
                       ┌────────────────┐               ┌────────────────┐
                       │ WordPress REST │◀──────────────│  utils/poster │
                       │  (publish)     │               │ (media + post)│
                       └────────────────┘               └────────────────┘
```

---

## 🛠️ Requirements

- **Python** ≥ 3.9
- A **WordPress** site with REST API enabled and an **Application Password**
- **OpenAI** API key
- **SerpAPI** key (for Google News results)
- Optional: **Telegram** API credentials if using Telegram sources

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## ⚙️ Configuration

Copy `.env_sample` to `.env` and set values:

```ini
# OpenAI
OPENAI_API_KEY=sk-...

# Google News (SerpAPI)
SERPAPI_KEY=...

# WordPress REST (Application Password recommended)
WP_API_BASE=https://your-site.com/wp-json/wp/v2
WP_USERNAME=your-admin-user
WP_APP_PASSWORD=abcd abcd abcd abcd

# Telegram (optional, for telegram_scraper)
api_id=123456
api_hash=your_telegram_api_hash
```

> If you use Basic Auth instead of Application Passwords, adapt `utils/poster.py` accordingly.

### Excel workbook (`blog_config.xlsx`)

Sheets:
- **`weekly_scheduler`** — a simple week grid (Mon–Sun) with topic names in cells. `main.py` looks at *today’s* column to decide which topic(s) to post.
- **`sources`** — registry of feeds and channels:
  - `desc_topic_primary`, `desc_topic_secondary`
  - `desc_channel` (`RSS`, `SERP`, `Telegram`)
  - `desc_name`, `desc_payload` (URL or channel handle)
  - `bool_visibility` (enable/disable)
  - `score_quality` (weighting)
  - `limit` (per-run cap)
- **`blocked_domains`** — domains to exclude (e.g. `finance.yahoo.com`, `bloomberg.com`).

---

## ▶️ Running

Default run for “today’s” topics:

```bash
python main.py
```

This will:
1. Load the weekly schedule for the current weekday.
2. Load matching **sources** (`bool_visibility == True`).
3. Collect research:
   - **SERP** (Google News via SerpAPI)
   - **RSS** feeds
   - **Telegram** channels (optional)
4. Build **news** + **history** prompts.
5. Call OpenAI to **write the article**, then **summarize** and **tag** it.
6. Save to **SQLite** (`articles.db`) and **publish** to WordPress.

Logs are written to `logs/operations.log`.

---

## 🧪 Local testing tips

- Run components in isolation:
  - `utils/scraper.py`: test `research()`, `scrapeRSS()` with a small `limit`.
  - `prompts/prompter.py`: verify token counts and history assembly.
  - `prompts/writer.py`: dry-run writing with shorter max tokens / temperature for speed.
  - `utils/poster.py`: publish to a **draft** post type first.
- Keep `blocked_domains` up to date to avoid paywalls/blocked content.
- Start with a “staging” WordPress site and low posting frequency.

---

## 🔐 Safety & compliance

- Respect robots.txt and site terms.
- Avoid copying large portions of paywalled content; prefer summarization and fair use.
- Attribute sources in generated text where appropriate.
- Add rate limits/backoff when scaling scraping.


---

## ⚠️ Disclaimer

This project is provided **as-is**. By using it, you agree to operate at your own responsibility and risk.  
- **Copyright and fair use**: Ensure that any generated or scraped content complies with local copyright laws and fair use policies.  
- **AI content policies**: Always review generated content before publishing to make sure it aligns with your site's editorial standards and AI policies.  
- **Web scraping**: Not all websites allow scraping. Check each site's terms of service and robots.txt before enabling sources.  
- The authors and contributors assume **no liability** for misuse of this codebase.

---

## 🙌 Acknowledgments

- [SerpAPI](https://serpapi.com/)
- [Telethon](https://docs.telethon.dev/)
- [newspaper3k](https://newspaper.readthedocs.io/)
- [WordPress REST API](https://developer.wordpress.org/rest-api/)
