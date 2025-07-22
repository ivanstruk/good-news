from dotenv import load_dotenv
import os
from newspaper import Article, Config, build, fulltext
import feedparser
import sqlite3
from datetime import datetime, timedelta
from telethon import TelegramClient
import asyncio
import time
import pandas as pd
from bs4 import BeautifulSoup
import email.utils
from openai import OpenAI
import requests
from requests.auth import HTTPBasicAuth
import yake
import string
from PIL import Image

load_dotenv() 

power_debug_mode = False

# -------- API Configurations --------
#Wordpress
WP_DOMAIN = os.getenv("domain")
WP_API_BASE = f"{WP_DOMAIN}/wp-json/wp/v2"
WP_POSTS_URL = f"{WP_API_BASE}/posts"
WP_USERNAME = "admin"
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
auth = HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)

#Telegram
telegram_api_id = int(os.getenv("api_id"))
telegram_api_hash = os.getenv("api_hash")
telegram_client = TelegramClient("mobile_session", telegram_api_id, telegram_api_hash)

# OpenAI
openai_key = os.getenv("openai_key")

# Load System Prompt
with open('system_prompt.txt', 'r') as file:
    content = file.read()
system_prompt = content

if power_debug_mode == True:
    print(" WARNING !!! DEBUG MODE ENABLED!!!")
    print("Current working directory:", os.getcwd())

# -------- Functions --------

def convert_to_sql_datetime(raw_date):
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

def convert_HTML(raw_html):
    soup = BeautifulSoup(raw_html, 'html.parser')
    text = soup.get_text()
    return text.strip()

def insert_article(article):
    try:
        with sqlite3.connect("articles.db", timeout=10) as conn:
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
        print(f"Database error: {e}")
        return 500

def fetch_rss(url, max_articles=10):
    rss_url = url
    feed = feedparser.parse(rss_url)
    articles = []
    for entry in feed.entries[:max_articles]:
        article = {
                "title" : entry.title,
                "content" : entry.summary,
                "channel" : "RSS",
                "source" : entry.get("source", {}).get("title", "Unknown Source"),
                "dt_published" : entry.get("published", ""),
                "link" : entry.link,
            }
        articles.append(article)

    return articles

async def get_latest_messages(channel_username, limit=30):
    messages = await telegram_client.get_messages(channel_username, limit=limit)

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

#Newspaper4k initiation
def get_article_texts(x):
    temp_db = []
    config = Config()
    config.browser_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    config.request_timeout = 10

    #print(f"Crawling source: {x['name']}")
    try:
        paper = build(x['url'], config=config, memoize_articles=False)

        for i, article in enumerate(paper.articles[:50]):
            try:
                article.download()
                article.parse()
                temp_db.append({
                    "source": x["name"],
                    "url": article.url,
                    "title": article.title,
                    "text": article.text,
                    "topic": x["category"],
                    "publish_date": article.publish_date,
                })
                #print(f"   [{i}] {article.title[:60]}...")
                time.sleep(1)
            except Exception as e:
                #print(f"   [{i}] Failed to parse article: {e}")
                time.sleep(1)
                
    except Exception as e:
        print(f" Failed to build source: {x['name']}")
        print(f" Error: {e}")

    return temp_db

def get_or_create_term(name, taxonomy):
    url = f"{WP_API_BASE}/{taxonomy}"

    # Try to find it
    response = requests.get(url, params={"search": name}, auth=auth)
    if response.status_code == 200:
        data = response.json()
        for item in data:
            if item["name"].lower() == name.lower():
                return item["id"]

    # If not found, try to create it
    response = requests.post(url, json={"name": name}, auth=auth)
    if response.status_code in [200, 201]:
        return response.json()["id"]
    else:
        raise Exception(f"Failed to create {taxonomy[:-1]} '{name}': {response.text}")

def fetchArchive(category, n):
    n = int(n)
    conn = sqlite3.connect("articles.db")
    q = "Select title, content from posted_articles where category='{}' Order by date_posted desc limit {}"
    archive = pd.read_sql_query(q.format(category, n), conn).to_dict(orient='records')

    if len(archive) == 0:
        return None

    helper = "Avoid repetition! You have recently written the following articles on this topic:"
    for x in archive:
        plain_content = convert_HTML(x["content"])
        post_ = "\n - {} : (excerpt) {}...".format(x["title"],plain_content.replace("\n"," "))
        helper+=post_

    helper += "\n\n"
    return helper

def post_to_wordpress(title, content, tags=[], categories=[], featured_image=None, status='publish'):
    tag_ids = [get_or_create_term(t, 'tags') for t in tags]
    category_ids = [get_or_create_term(c, 'categories') for c in categories]

    post_data = {
        "title": title,
        "content": content,
        "status": status,
        "tags": tag_ids,
        "categories": category_ids
    }
    if featured_image:
        post_data["featured_media"] = featured_image

    response = requests.post(WP_POSTS_URL, auth=auth, json=post_data)

    if response.status_code == 201:
        print("✅ Article posted successfully!")
        return response.json()
    else:
        print(f"❌ Failed to post: {response.status_code}")
        print(response.text)
        return None

def extract_title(article_str):
    split_token = '<ul>'
    if split_token in article_str:
        title = article_str.split(split_token)[0].strip()
        return title
    # Fallback: if no <ul> found, return the whole string trimmed
    return article_str.strip()
    
def clean_tag(tag):
    return tag.translate(str.maketrans('', '', string.punctuation)).strip()
    
def get_tags(body_text):
    soup = BeautifulSoup(body_text, "html.parser")
    body_text = soup.get_text(separator="\n").strip()
    kw_extractor = yake.KeywordExtractor(lan="en", n=1, top=5)
    keywords = kw_extractor.extract_keywords(body_text)
    tags = [clean_tag(kw[0]) for kw in keywords if clean_tag(kw[0])]
    return tags

def generate_feature_image(prompt: str) -> str:
    # Internal settings
    size = "1024x1024"
    model = "dall-e-3"
    retries = 3
    verbose = power_debug_mode  # Set to True for debugging output
    ai_client = OpenAI(api_key=openai_key)
    for attempt in range(retries):
        try:
            response = ai_client.images.generate(
                prompt=prompt,
                model=model,
                size=size,
                n=1
            )
            return response.data[0].url
        except Exception as e:
            if verbose:
                print(f"[Attempt {attempt + 1}/{retries}] Image generation failed: {e}")
    return None

def download_image(image_url):
    if power_debug_mode == True:
        print("Downloading image...")

    r = requests.get(image_url)
    r.raise_for_status()
    with open("featured_image.png", "wb") as f:
        f.write(r.content)

def crop_to_size(path):
    image = Image.open(path)
    
    # Define crop area
    left = 0
    top = (1024 - 537) // 2  # Crop equally from top and bottom
    right = 1024
    bottom = top + 537
    
    # Crop the image
    cropped_image = image.crop((left, top, right, bottom))
    cropped_image.save("featured_image.png")

    return None

def upload_featured_image(image_path):
    filename = os.path.basename(image_path)
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type": "image/png"
    }

    with open(image_path, 'rb') as img:
        response = requests.post(
            f"{WP_API_BASE}/media",
            headers=headers,
            auth=auth,
            data=img
        )

    if response.status_code in [200, 201]:
        media_id = response.json().get("id")
        print(f"✅ Uploaded image. Media ID: {media_id}")
        return media_id
    else:
        print(f"❌ Image upload failed: {response.status_code}")
        print(response.text)
        return None

def save_generated_article(title, content, category, db_path="articles.db"):
    
    preview_content = content[:400]

    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            cursor = conn.cursor()

            # Create table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posted_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_posted TEXT,
                    title TEXT,
                    content TEXT,
                    category TEXT
                );
            """)

            # Insert the record
            cursor.execute("""
                INSERT INTO posted_articles (
                    date_posted, title, content, category
                ) VALUES (?, ?, ?, ?);
            """, (
                datetime.utcnow().isoformat(),
                title,
                preview_content,
                category
            ))

            conn.commit()
            print("✅ Generated article saved to database.")
    except Exception as e:
        print(f"❌ Error saving generated article: {e}")


async def main():
    print("Fetching sources...")
    print("Starting Telegram client...")
    await telegram_client.start() 
    print("✅ Telegram client started.")


    if not await telegram_client.is_user_authorized():
        print("❌ Not authorized. You need to re-login using a terminal-based login script.")
        return

    print("✅ Telegram client started and authorized.")

    # Sources
    sources = pd.read_excel("sources.xlsx", sheet_name = 'sources').to_dict(orient='records')
    counter=0

    if power_debug_mode == False:
        # Scraping doesn't run during debug mode.
        for source in sources:
            if source["bool_fetch_articles"] == True:
                print("--> Fetching from {} ({})".format(source["name"], source["channel"]))
                channel = source["channel"]

                if channel == 'RSS':
                    rss = fetch_rss(source["url"],20)
                    for y in rss:
                        content = y["content"]
                        try:
                            content = convert_HTML(content)
                        except:
                            pass

                        article = {
                            "title" : y["title"],
                            "content" : content,
                            "channel" : y["channel"],
                            "source" : source["name"],
                            "topic" : source["category"],
                            "link" : y["link"],
                            "dt_published" : convert_to_sql_datetime(y["dt_published"])    
                        }
                        response = insert_article(article)
                        if response == 200:
                            #counter+=1
                            pass
                            
                elif channel == 'Telegram':
                    telegram_channel = source["url"].replace("https://t.me/","")
                    msgs = await get_latest_messages(telegram_channel)
                    
                    for i in msgs:
                        article = {
                            "title" : i["id"],
                            "content" : i["text"],
                            "channel" : source["channel"],
                            "source" : source["name"],
                            "topic" : source["category"],
                            "link" : "{}/{}".format(source["url"],i["id"]),
                            "dt_published" : convert_to_sql_datetime(i["date"])    
                        }
                        response = insert_article(article)
                        if response == 200:
                            counter+=1
                        
                elif channel == 'News':
                    arts = get_article_texts(source)
                    for i in arts:
                        try:
                            article = {
                                "title" : i["title"],
                                "content" : i["text"],
                                "channel" : source["channel"],
                                "source" : source["name"],
                                "topic" : source["category"],
                                "link" : i["url"],
                                "dt_published" : convert_to_sql_datetime(i["publish_date"])    
                            }
                            response = insert_article(article)
                            if response == 200:
                                counter+=1
                        except:
                            pass

    print("Articles added: {}".format(counter))
    generate_and_post()

def generate_and_post():
    
    #Fetch Unique Categories
    category_properties = pd.read_excel("sources.xlsx", sheet_name='category_properties')
    category_properties = category_properties[category_properties["bool_post"]==True].to_dict(orient='records')

    # Generation per category
    for cat in category_properties:
        category = cat["category"]
        user_prompt_context = cat["prompt_topic"]

        #Add post history to prevent repetition.
        history_add = fetchArchive(category,5)
        if history_add != None:
            user_prompt_context += history_add

        conn = sqlite3.connect("articles.db")
        df = pd.read_sql_query("""
            SELECT *
            FROM articles
            WHERE 1=1 AND topic = '{}'
            ORDER BY dt_published DESC
            LIMIT 10
        """.format(category), conn)

        dump = df.to_dict(orient='records')
        counter = 0
        
        for x in dump:
            counter+=1
            prompter = """Brief #{} \nSource: {}, originating from {} \nPublished: {} \n\n>>>TRANSCRIPT START<<< \nTitle: {} \n{}\n>>>TRANSCRIPT END<<< \n\n\n""".format(
                counter,
                x["source"],
                x["channel"],
                x["dt_published"],
                x["title"],
                x["content"]
                )
            user_prompt_context += prompter

        #OpenAI plugin
        ai_client = OpenAI(api_key=openai_key)
        response = ai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt_context}
            ],
            temperature=0.3,
            max_tokens=2048
        )
        
        copy = response.choices[0].message.content
        title = extract_title(copy)
        body = copy.split(title)[1]
        tags = get_tags(body)

        # Image generation starts here, with first getting the prompt
        image_prompt = cat["prompt_image"]
        if cat["bool_var_exists"] == True:
            image_prompt = image_prompt.format(title)

        # Then we generate the image, fetching its OpenAI URL and downloading it.
        image_url = generate_feature_image(image_prompt)

        # This image needs to be uploaded before it can be addressed.         
        if image_url == None:
            print("--> Image URL is None")
            media_id = None
        else:
            download_image(image_url)
            crop_to_size("featured_image.png")
            media_id = upload_featured_image("featured_image.png")
        
        post_to_wordpress(title, body, tags=tags, categories=[category], featured_image=media_id)
        save_generated_article(title, body, category, db_path="articles.db")
    
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()

    loop = asyncio.get_event_loop()

    async def shutdown():
        if telegram_client.is_connected():
            await telegram_client.disconnect()

    async def runner():
        await telegram_client.connect()

        if not await telegram_client.is_user_authorized():
            print("❌ Not authorized. Run the login script first.")
        else:
            print("✅ Telegram client authorized. Starting main...")
            await main()

        await shutdown()

    loop.run_until_complete(runner())