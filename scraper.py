from dotenv import load_dotenv
import pandas as pd
from pathlib import Path
import os
from db_utils import insert_article, to_sql_datetime
import requests
from newspaper import Article
from newspaper import Config
import feedparser
import time
from bs4 import BeautifulSoup
from logger import logger
from newspaper import Article, Config, build, fulltext

base_dir = Path(__file__).resolve().parent
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

#Defining some blocked domains.
blocked_sources = pd.read_excel(os.path.join(base_dir,"blog_config.xlsx"), sheet_name = 'blocked_domains')["Domains"].to_list()

## Dependencies

def get_article(url):
    config = Config()
    config.browser_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    config.request_timeout = 10
    #print(f"Crawling source: {x['name']}")
    
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
        time.sleep(4)  # Optional polite delay
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
    except:
        logger.info("Exception: Failed to extract domain from URL")
        return None
        
def convert_HTML(raw_html):
    soup = BeautifulSoup(raw_html, 'html.parser')
    text = soup.get_text()
    return text.strip()

def serpapi_search(topic, api_key, num_results=5):
    url = "https://serpapi.com/search"
    serp_api_key = os.getenv("serp_api_key")
    params = {
        "engine": "google",     # Use Google search engine
        "q": topic,             # Search topic
        "tbm": "nws",           # News tab
        "num": num_results,     # How many news results to return
        "api_key": serp_api_key
    }

    response = requests.get(url, params=params)
    response.raise_for_status()  # Raise error if request fails

    data = response.json()

    # Extract relevant info
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

## Core
def research(query, topic, results=5):
    research = []
    logger.info(f"research(): searching SERP for {query}")
    """
    Search for recent news on a given topic in SERP.

    Args:
        topic (str): The search keyword/topic.
        results (int, optional): Number of results to return (default 5).

    Returns:
        list: A list of article dictionaries.
    """
    # Validate 'results'
    if not isinstance(results, int) or results <= 0:
        logger.info("Warning: 'results' must be a positive integer. Defaulting to 5.")
        results = 5

    # Validate 'query'
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")
    
    counter=0
    try:
        results = serpapi_search(topic,20)
        blocked_sources = ["finance.yahoo.com", "bloomberg.com"]
        
        for x in results:
            url = x.get("link", "").lower()
            if any(bad in url for bad in blocked_sources):
                continue  # Skip blocked domains

            art = get_article(x["link"])
            if art == None:
                continue
                
            my_article = {
                "title" : art["title"],
                "content" : convert_HTML(art["text"]),
                "channel" : "SERP",
                "source" : get_domain(url),
                "topic" : topic,
                "link" : url,
                "dt_published" : to_sql_datetime(art["publish_date"])    
            }
            research.append(my_article)
            response = insert_article(my_article)
            if response == 200:
                counter+=1
        pass
    except Exception as e:
        logger.info(f"Error in research(): {e}")

    logger.info(f"Found {counter} new articles")
    return research

def scrapeRSS(url, topic, max_articles=10):
    
    logger.info(f"Scraping RSS: {url}")
    counter=0
    research = []
    feed = feedparser.parse(url)
    
    for entry in feed.entries[:max_articles]:

        entry_content = entry.summary
        try:
            entry_content = convert_HTML(entry_content)
        except:
            pass

        article = {
                "title" : entry.title,
                "content" : entry_content,
                "channel" : "RSS",
                "source" : entry.get("source", {}).get("title", "Unknown Source"),
                "topic" : topic,
                "link" : entry.link,
                "dt_published" : to_sql_datetime(entry.get("published", ""))
            }
        research.append(article)
        response = insert_article(article)
        if response == 200:
            counter+=1
            pass

    logger.info(f"Found {counter} new articles")
    return research

def fetchNews(source):
    name_name = source["desc_name"]
    logger.info(f"Fetching News from {name_name}")
    research = []
    config = Config()
    config.browser_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    config.request_timeout = 10
    counter=0
    #print(f"Crawling source: {x['name']}")
    try:
        paper = build(source['desc_payload'], config=config, memoize_articles=False)

        for i, article in enumerate(paper.articles[:50]):
            try:
                article.download()
                article.parse()
                article_local = {
                    "title": article.title,
                    "content": article.text,
                    "channel": "News",
                    "source": source["desc_name"],
                    "topic" : x["desc_topic_primary"],
                    "link": article.url,
                    "dt_published": to_sql_datetime(article.publish_date),
                }
                research.append(article_local)
                response = insert_article(article)
                if response == 200:
                    counter+=1
                    pass

                time.sleep(1)
            except Exception as e:
                time.sleep(1)
                
    except Exception as e:
        logger.info(f"fetchNews() - Failed to build source: {x['name']}")
        logger.info(f"fetchNews() - Error: {e}")

    logger.info(f"Found {counter} new articles")
    return research


