import sys
from pathlib import Path

# Ensure project root is in sys.path so imports like "from utils.logger" work
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from utils.logger import logger
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import requests
from PIL import Image, ImageDraw, ImageFont
from dataclasses import dataclass
from typing import List, Tuple, Optional

# === Setup ===
base_dir = Path(__file__).resolve().parent.parent
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# OpenAI client
openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    logger.error("OPENAI_API_KEY is not set in the environment.")
client = OpenAI(api_key=openai_key)


# === Main Functions ===

def generate_image_prompt(article_summary: str, system_prompt: str) -> str:
    # Prepare messages for Chat Completions
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Article summary:\n{article_summary.strip()}\n\nWrite the final image prompt."},
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # good balance of speed and creativity
        messages=messages,
        temperature=0.8,      # slightly creative to vary scene composition
    )
    # Extract the prompt text
    return response.choices[0].message.content.strip()

def generate_image(prompt: str) -> str:
    """
    Generate an image from a text prompt using OpenAI's image API.

    Args:
        prompt (str): The description of the image to generate.

    Returns:
        str | None: The URL of the generated image, or None if failed.
    """
    logger.info("Starting image generation...")

    #size = "1024x1024"
    size = "1792x1024"
    model = "dall-e-3"
    retries = 2

    for attempt in range(1, retries + 1):
        try:
            response = client.images.generate(
                prompt=prompt,
                model=model,
                size=size,
                n=1
            )
            image_url = response.data[0].url
            logger.info("Image generated successfully.")
            return image_url
        except Exception as e:
            logger.warning(f"[Attempt {attempt}/{retries}] Image generation failed: {e}")

    logger.error("All image generation attempts failed.")
    return None


def download_image(image_url: str) -> str:
    """
    Download an image from a URL and save it as featured_image.jpg.

    Args:
        image_url (str): The URL of the image to download.

    Returns:
        str: Path to the saved image file.
    """
    logger.info("Downloading image...")

    try:
        response = requests.get(image_url)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        raise

    file_path = os.path.join(base_dir, "featured_image.jpg")
    try:
        with open(file_path, "wb") as f:
            f.write(response.content)
        logger.info(f"Image saved to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save downloaded image: {e}")
        raise

    return file_path


def crop_to_size(path: str) -> None:
    """
    Crop an image to 1024x537 and overwrite it.
    """
    logger.info(f"Cropping image: {path}")

    try:
        image = Image.open(path)

        # Define crop area
        left = 0
        top = (1024 - 537) // 2  # Crop equally from top and bottom
        right = 1024
        bottom = top + 537

        cropped_image = image.crop((left, top, right, bottom))
        save_path = os.path.join(base_dir, "featured_image.jpg")
        cropped_image.save(save_path)

        logger.info(f"Cropped image saved to {save_path}")
    except Exception as e:
        logger.error(f"Failed to crop image: {e}")
        raise

def process_image(system_prompt: str, article_summary: str) -> bool:

    logger.info("Starting image pipeline...")
    # The real first step is generating the prompt
    prompt = generate_image_prompt(system_prompt, article_summary)

    try:
        # 1) Generate
        image_url = generate_image(prompt)
        if not image_url:
            logger.error("Image generation failed (no URL).")
            return False

        # 2) Download
        downloaded_path = download_image(image_url)

        featured_path = base_dir / "featured_image.jpg"

        logger.info(f"Image saved at: {featured_path}")
        logger.info("Image pipeline finished successfully.")
        return True

    except Exception as e:
        logger.error(f"Image pipeline failed: {e}")
        return False