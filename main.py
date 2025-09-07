from logger import logger
from scraper import research, scrapeRSS, fetchNews
from telegram_scraper import fetchTelegram
import pandas as pd
import datetime
from prompts.prompter import build_news_prompt, build_history_prompt
from prompts.writer import write_article

logger.info("Modules imported.")

# Weekly Schedule
schedule_sheet = pd.read_excel(
    "blog_config.xlsx",
    sheet_name="weekly_scheduler",
    skiprows=3,     # Skip rows above row 4
    usecols="B:H",  # Read only columns B through H
    nrows=10        # Read 10 rows (B4:H13)
)
schedule = [
    {"Weekday": col, "Topics": schedule_sheet[col].dropna().tolist()}
    for col in schedule_sheet.columns
]

weekday = datetime.datetime.today().strftime("%A")
topic_agenda = schedule_sheet[weekday].dropna().tolist() #defines the topics relevant to current weekday

logger.info("Schedule determined. Today is {}".format(weekday))

# Topics
sources = pd.read_excel("blog_config.xlsx", sheet_name="sources").to_dict(orient='records')
sources = [s for s in sources if s["bool_visibility"]==True]

# Initializing script...

for topic in topic_agenda:
    logger.info("Topic pool, topic: {}".format(topic))

    temp_research_db = []

    # Starting to research latest sources
    filtered_sources = [s for s in sources if s["desc_topic_primary"]==topic]
    for source in filtered_sources:
        channel = source["desc_channel"]

        if channel == "SERP":
            SERP_articles = research(source["desc_payload"], source["desc_topic_primary"], source["limit"])
            if len(SERP_articles) > 0:
                temp_research_db.extend(SERP_articles)

        elif channel == "RSS":
            RSS_articles = scrapeRSS(source["desc_payload"], source["desc_topic_primary"], source["limit"])
            if len(RSS_articles) > 0:
                temp_research_db.extend(RSS_articles)

        #elif channel == "News":
        #    news_articles = fetchNews(source)
        #    if len(news_articles) > 0:
        #        temp_research_db.extend(news_articles)
        #
        elif channel == "Telegram":
            telegram_messages = fetchNews(source)
            if len(telegram_messages) > 0:
                temp_research_db.extend(telegram_messages)

        else:
            logger.info("Channel unrecognized: {}".format(channel))
            pass
    
    news = build_news_prompt(temp_research_db, 10000)
    past_works = build_history_prompt(topic, limit=10)


    write_article(news,past_works)
