import os
import sys
import tiktoken
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from db_utils import fetch_posts


# Tiktoken
def count_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


# News History
def fill_news_article_template(number, title, source, content):
    template_path = os.path.join(os.path.dirname(__file__), "article_template.txt")
    with open(template_path, "r", encoding="utf-8") as file:
        template = file.read()
    filled_article = template.format(
        number=number,
        title=title,
        source=source,
        content=content
    )
    return filled_article


def build_news_prompt(research_list, max_token_limit=10000):
    research = pd.DataFrame(research_list)
    research = research.sort_values(by='dt_published', ascending=False).to_dict(orient='records')

    prompt_part_news = ""
    n = 0
    for i in research:
        prompt_token_count = count_tokens(prompt_part_news)
        
        source =  "{} ({})".format(i["source"], i["channel"])
        n+=1
        more_news = fill_news_article_template(n, i["title"], source, i["content"])
        more_news_token_count = count_tokens(more_news)
        if prompt_token_count + more_news_token_count > max_token_limit:
            print("Stopping after {} sources added. Tokens used: {}".format(n-1, more_news_token_count+prompt_token_count))
            break
        
        prompt_part_news += more_news
        prompt_part_news += "\n"

    return prompt_part_news

# Post History
def fill_post_template(number, title, summary):
    template_path = os.path.join(os.path.dirname(__file__), "past_article_template.txt")
    with open(template_path, "r", encoding="utf-8") as file:
        template = file.read()
    
    filled_article = template.format(
        number=number,
        title=title,
        summary=summary
    )
    return filled_article

def build_history_prompt(topic, limit=10):
    history_prompt = ""
    n = 0

    posts = fetch_posts(topic)
    if len(posts) != 0:
        for i in posts:
            n+=1
            post = fill_post_template(n, i["title"], i["summary"])
            
            if n > limit:
                break
            else:
                history_prompt += post
                history_prompt += "\n"
    else:
        history_prompt = None

    return history_prompt