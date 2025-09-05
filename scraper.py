

topic_whitelist = [
    "blockchain",
    "ai",
    "economy",
    "sports",
    "politics",
    "climate"
]

def research(topic, results=5):
    """
    Search for recent news on a given topic.

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
        keywords = extract_keywords(search_term)
        k_len=0
        where_clause = ""
        for k in keywords:
            k_len+=1
            print(k)
            if k_len > 1:
                
                where_clause+= "OR content LIKE '%{}%' COLLATE NOCASE ".format(k)
            else:
                where_clause+="content LIKE '%{}%' COLLATE NOCASE "

        conn = sqlite3.connect(os.path.join(base_dir,"articles.db"))
        
        df = pd.read_sql_query("""
            SELECT 
                title,
                content,
                channel,
                source,
                topic,
                link,
                dt_published
                
            FROM articles
            WHERE 1=1
            AND ({})

            ORDER BY dt_published DESC
            LIMIT 5
        """.format(where_clause), conn)

        research.extend(df.to_dict(orient='records'))
        
        results = serpapi_search(search_term,20)
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

    return articles