import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Paths
base_dir = Path(__file__).resolve().parent.parent
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# OpenAI client
openai_key = os.getenv("OPENAI_API_KEY")  # matches .env convention
client = OpenAI(api_key=openai_key)

def write_article(research, post_history):
    template_path = os.path.join(os.path.dirname(__file__), "writer_template.txt")
    with open(template_path, "r", encoding="utf-8") as file:
        template = file.read()

    if post_history is None:
        filled_prompt = template.format(
            articles=research,
            post_header="",
            post_history=""
        )
    else:
        post_header = "=== PAST ARTICLES (SUMMARIES) ==="
        filled_prompt = template.format(
            articles=research,
            post_header=post_header,
            post_history=post_history
        )

    # Save prompt for logging
    save_dir = os.path.join(os.path.dirname(__file__), "logged_prompts")
    os.makedirs(save_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"article_prompt_{timestamp}.txt"
    file_path = os.path.join(save_dir, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(filled_prompt)

    # Load system prompt
    system_prompt_path = os.path.join(os.path.dirname(__file__), "writer_system_prompt.txt")
    with open(system_prompt_path, "r", encoding="utf-8") as file:
        system_prompt = file.read()

    # Call OpenAI
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": filled_prompt}
        ],
        temperature=0.4,
        max_tokens=4096
    )

    return response.choices[0].message.content
