from dotenv import load_dotenv
import pandas as pd
from pathlib import Path
import os
from urllib.parse import urlparse
from utils.db_utils import insert_article, to_sql_datetime
import requests
from newspaper import Article, Config, build
import feedparser
import time
from bs4 import BeautifulSoup
from utils.logger import logger

# === Paths ===
base_dir = Path(__file__).resolve().parent.parent  # project root
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# Load blocked domains from config
blocked_sources_file = os.path.join(base_dir, "blog_config.xlsx")
blocked_sources = pd.read_excel(blocked_sources_file, sheet_name='blocked_domains')["Domains"].to_list()


# === Helper Functions ===
def get_article(url):
    config = Config()
    config.browser_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    config.request_timeout = 10

    try:
        article = Article(url, config=config)
        article.download()
        article.parse()
        result = {
            "url": article.url,
            "title": article.title,
            "text": article.text,
            "publish_date": article.publish_date,
        }
        time.sleep(4)  # polite delay
        return result
    except Exception as e:
        logger.info(f"Failed to fetch article: {url}")
        logger.info(f"Error: {e}")
        return None


def get_domain(url):
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        parsed_url = urlparse(url)
        return parsed_url.netloc
    except Exception:
        logger.info("Exception: Failed to extract domain from URL")
        return None


def convert_HTML(raw_html):
    soup = BeautifulSoup(raw_html, 'html.parser')
    text = soup.get_text()
    return text.strip()


def serpapi_search(topic, num_results=5):
    url = "https://serpapi.com/search"
    serp_api_key = os.getenv("SERPAPI_KEY")
    params = {
        "engine": "google",
        "q": topic,
        "tbm": "nws",
        "num": num_results,
        "api_key": serp_api_key
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    articles = []
    for item in data.get("news_results", []):
        articles.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "snippet": item.get("snippet"),
            "source": item.get("source"),
            "date": item.get("date")
        })
    return articles


# === Core Functions ===
def research(query, topic, results=5):
    research_list = []
    logger.info(f"research(): searching SERP for {query}")

    if not isinstance(results, int) or results <= 0:
        logger.info("Warning: 'results' must be a positive integer. Defaulting to 5.")
        results = 5
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")

    counter = 0
    try:
        search_results = serpapi_search(topic, results)
        blocked = ["finance.yahoo.com", "bloomberg.com"]

        for x in search_results:
            url = x.get("link", "").lower()
            if any(bad in url for bad in blocked):
                continue

            art = get_article(x["link"])
            if art is None:
                continue

            my_article = {
                "title": art["title"],
                "content": convert_HTML(art["text"]),
                "channel": "SERP",
                "source": get_domain(url),
                "topic": topic,
                "link": url,
                "dt_published": to_sql_datetime(art["publish_date"])
            }
            research_list.append(my_article)
            response = insert_article(my_article)
            if response == 200:
                counter += 1

    except Exception as e:
        logger.info(f"Error in research(): {e}")

    logger.info(f"Found {counter} new articles")
    return research_list


def scrapeRSS(url, topic, max_articles=10):
    logger.info(f"Scraping RSS: {url}")
    counter = 0
    research_list = []

    feed = feedparser.parse(url)
    for entry in feed.entries[:max_articles]:
        entry_content = entry.get("summary", "")
        try:
            entry_content = convert_HTML(entry_content)
        except:
            pass

        article = {
            "title": entry.title,
            "content": entry_content,
            "channel": "RSS",
            "source": entry.get("source", {}).get("title", "Unknown Source"),
            "topic": topic,
            "link": entry.link,
            "dt_published": to_sql_datetime(entry.get("published", ""))
        }
        research_list.append(article)
        response = insert_article(article)
        if response == 200:
            counter += 1

    logger.info(f"Found {counter} new articles")
    return research_list


def fetchNews(source):
    """
    Build a newspaper source and fetch its articles.
    """
    name_name = source["desc_name"]
    logger.info(f"Fetching News from {name_name}")
    research_list = []
    config = Config()
    config.browser_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    config.request_timeout = 10
    counter = 0

    try:
        paper = build(source['desc_payload'], config=config, memoize_articles=False)

        for article in paper.articles[:50]:
            try:
                article.download()
                article.parse()
                article_local = {
                    "title": article.title,
                    "content": article.text,
                    "channel": "News",
                    "source": source["desc_name"],
                    "topic": source["desc_topic_primary"],
                    "link": article.url,
                    "dt_published": to_sql_datetime(article.publish_date),
                }
                research_list.append(article_local)
                response = insert_article(article_local)
                if response == 200:
                    counter += 1
                time.sleep(1)
            except Exception as e:
                logger.info(f"fetchNews() - Failed parsing article: {e}")
                time.sleep(1)

    except Exception as e:
        logger.info(f"fetchNews() - Failed to build source: {source['desc_name']}")
        logger.info(f"fetchNews() - Error: {e}")

    logger.info(f"Found {counter} new articles")
    return research_list
