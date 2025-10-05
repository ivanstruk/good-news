from utils.logger import logger
from datetime import datetime, timedelta
import sqlite3
import os
import email.utils
from pathlib import Path
import pandas as pd

# Base directory of the project (one level above utils folder)
base_dir = Path(__file__).resolve().parent.parent

# Default database path
DB_PATH = os.path.join(base_dir, "articles.db")


def insert_article(article, db_path=DB_PATH):
    """
    Insert a scraped article into the articles table.
    """
    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            cursor = conn.cursor()

            # Check if article already exists by link or title
            cursor.execute("""
                SELECT 1 FROM articles
                WHERE link = ? OR title = ?
            """, (article.get("link"), article.get("title")))
            exists = cursor.fetchone()

            if exists:
                return 400  # Already exists

            # Insert new article
            query = '''
            INSERT OR IGNORE INTO articles (
                title, content, channel, source, topic, link, dt_published, dt_added
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            '''
            cursor.execute(query, (
                article.get("title"),
                article.get("content"),
                article.get("channel"),
                article.get("source"),
                article.get("topic"),
                article.get("link"),
                article.get("dt_published"),
                datetime.utcnow().isoformat()
            ))
            conn.commit()
            return 200

    except sqlite3.OperationalError as e:
        logger.info(f"[db_utils] - Database insert error: {e}")
        return 500


def to_sql_datetime(raw_date):
    """
    Convert a string or datetime into a SQL-compatible datetime string.
    """
    if isinstance(raw_date, datetime):
        return raw_date.strftime('%Y-%m-%d %H:%M:%S')

    try:
        dt = email.utils.parsedate_to_datetime(raw_date)
        if dt:
            return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, AttributeError):
        pass

    try:
        dt = datetime.fromisoformat(raw_date)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        pass

    # Fallback
    fallback_time = datetime.utcnow() - timedelta(hours=1)
    return fallback_time.strftime('%Y-%m-%d %H:%M:%S')


def fetch_posts(category, limit=100, db_path=DB_PATH):
    """
    Fetch the most recent posts in a category as a list of dicts.
    """
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(f"""
            SELECT *
            FROM posted_articles
            WHERE category = ?
            ORDER BY dt_published DESC
            LIMIT ?
        """, conn, params=(category, limit))

    return df.to_dict(orient='records')


def save_generated_article(
    title, content, topic, category, summary, link, dt_published=None,
    db_path=DB_PATH
):
    """
    Save a generated article to the posted_articles table.
    """
    if dt_published is None:
        dt_published = datetime.utcnow().isoformat()

    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            cursor = conn.cursor()

            # Create table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posted_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    content TEXT,
                    topic TEXT,
                    category TEXT,
                    summary TEXT,
                    link TEXT UNIQUE,
                    dt_published TEXT
                )
            ''')

            # Insert the record
            cursor.execute("""
                INSERT INTO posted_articles (
                    title, content, topic, category, summary, link, dt_published
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                content,
                topic,
                category,
                summary,
                link,
                dt_published
            ))

            conn.commit()
            logger.info("Generated article saved to database.")

    except sqlite3.IntegrityError:
        logger.warning(f"Article with link '{link}' already exists.")
    except Exception as e:
        logger.error(f"Error saving generated article: {e}")
