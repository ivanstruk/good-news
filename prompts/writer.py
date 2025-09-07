import os
from datetime import datetime


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

    # Hard-coded save directory: "logged prompts" next to writer.py
    save_dir = os.path.join(os.path.dirname(__file__), "logged prompts")
    os.makedirs(save_dir, exist_ok=True)

    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"article_prompt_{timestamp}.txt"
    file_path = os.path.join(save_dir, filename)

    # Save to file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(filled_prompt)

    return file_path
