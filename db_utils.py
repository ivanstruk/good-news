from logger import logger
from db_utils import insert_article, to_sql_datetime
from datetime import datetime, timedelta
import sqlite3
import os
import email.utils
from pathlib import Path


base_dir = Path(__file__).resolve().parent

def insert_article(article):
    try:
        with sqlite3.connect(os.path.join(base_dir,"articles.db"), timeout=10) as conn:
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
        logger.info(f"[write_news.py] - Database insert error: {e}")
        return 500

def to_sql_datetime(raw_date):
    # If already a datetime object
    if isinstance(raw_date, datetime):
        return raw_date.strftime('%Y-%m-%d %H:%M:%S')

    try:
        dt = email.utils.parsedate_to_datetime(raw_date)
        if dt:
            return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, AttributeError):
        pass

    # Try parsing ISO format: "2025-07-17T15:05:00"
    try:
        dt = datetime.fromisoformat(raw_date)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        pass

    fallback_time = datetime.utcnow() - timedelta(hours=1)
    return fallback_time.strftime('%Y-%m-%d %H:%M:%S')
