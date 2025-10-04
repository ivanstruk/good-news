from utils.logger import logger
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import requests
from PIL import Image


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
def generate_image(prompt: str) -> str:
    """
    Generate an image from a text prompt using OpenAI's image API.

    Args:
        prompt (str): The description of the image to generate.

    Returns:
        str | None: The URL of the generated image, or None if failed.
    """
    logger.info("Starting image generation...")

    size = "1024x1024"
    model = "dall-e-3"
    retries = 3

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

    Args:
        path (str): Path to the image file.

    Returns:
        None
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

def process_image(prompt: str) -> bool:
    """
    Full pipeline: generate an image, download it, crop to size,
    and overwrite as featured_image.jpg.

    Args:
        prompt (str): Text prompt for image generation.

    Returns:
        bool: True if successful, False otherwise.
    """
    logger.info("Starting full image pipeline...")

    # Step 1: Generate image
    image_url = generate_image(prompt)
    if not image_url:
        logger.error("Image generation failed. Aborting pipeline.")
        return False

    # Step 2: Download image
    try:
        file_path = download_image(image_url)
    except Exception as e:
        logger.error(f"Image download failed: {e}")
        return False

    # Step 3: Crop image
    try:
        crop_to_size(file_path)
    except Exception as e:
        logger.error(f"Image cropping failed: {e}")
        return False

    logger.info("Image pipeline completed successfully.")
    return True