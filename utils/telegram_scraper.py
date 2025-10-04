from datetime import datetime
from telethon import TelegramClient
import asyncio
from dotenv import load_dotenv
import os
from utils.logger import logger

# Load environment variables
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# Telegram credentials
telegram_api_id = int(os.getenv("api_id", "0"))
telegram_api_hash = os.getenv("api_hash", "")
session_path = os.path.join(base_dir, "mobile_session")


# --- Internal async function ---
async def _get_latest_messages(channel_username, limit=10):
    client = TelegramClient(session_path, telegram_api_id, telegram_api_hash)

    try:
        await client.start()  # Connects and handles auth
        if not await client.is_user_authorized():
            logger.error("❌ Telegram client not authorized. Run the login script first.")
            return []

        messages = await client.get_messages(channel_username, limit=limit)
        result = []
        for msg in messages:
            if msg.text:
                result.append({
                    "id": msg.id,
                    "date": msg.date.isoformat(),
                    "text": msg.text,
                    "channel": channel_username
                })
        return result

    except Exception as e:
        logger.error(f"⚠️ Error fetching messages: {e}")
        return []
    finally:
        await client.disconnect()


# --- Public function ---
def fetchTelegram(source):
    telegram_channel = source["payload"].replace("https://t.me/", "")

    # Run async function in a blocking way (main.py can just call fetchTelegram normally)
    messages = asyncio.run(_get_latest_messages(telegram_channel, limit=source["limit"]))

    tmp_db = []
    for msg in messages:
        article = {
            "title": str(msg["id"]),
            "content": msg["text"],
            "channel": "Telegram",
            "source": source["desc_name"],
            "topic": source["desc_topic_primary"],
            "link": f"{source['desc_payload']}/{msg['id']}",
            "dt_published": to_sql_datetime(msg["date"])
        }
        tmp_db.append(article)

        response = insert_article(article)
        if response == 200:
            logger.info(f"✅ Inserted article {msg['id']} from {source['name']}")

    return tmp_db
