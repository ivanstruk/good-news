from dotenv import load_dotenv
import pandas as pd
from pathlib import Path
import os
from db_utils import insert_article


base_dir = Path(__file__).resolve().parent
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)


#Defining some blocked domains.
blocked_sources = pd.read_excel(os.path.join(base_dir,"sources.xlsx"), sheet_name = 'blocked_domains')["Domains"].to_list()

## Dependencies

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


def research(topic, results=5):
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
        print("Warning: 'results' must be a positive integer. Defaulting to 5.")
        results = 5

    # Validate 'topic'
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("topic must be a non-empty string.")

    research = []
        
    results = serpapi_search(topic,20)
    blocked_sources = ["finance.yahoo.com", "bloomberg.com"]
    counter=0
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
            "channel" : "News",
            "source" : get_domain(url),
            "topic" : "On-Demand",
            "link" : url,
            "dt_published" : convert_to_sql_datetime(art["publish_date"])    
        }
        research.append(my_article)
        response = insert_article(my_article)
        if response == 200:
            counter+=1
                
    try:
        # TODO: implement research logic
        pass
    except Exception as e:
        print(f"Error in research: {e}")

    return research