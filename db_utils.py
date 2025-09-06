from logger import logger
from datetime import datetime, timedelta
import sqlite3
import os


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
