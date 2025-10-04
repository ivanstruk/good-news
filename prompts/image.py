


def generate_image(prompt: str) -> str:
    # Internal settings
    size = "1024x1024"
    model = "dall-e-3"
    retries = 3
    verbose = power_debug_mode  # Set to True for debugging output
    ai_client = OpenAI(api_key=openai_key)
    for attempt in range(retries):
        try:
            response = ai_client.images.generate(
                prompt=prompt,
                model=model,
                size=size,
                n=1
            )
            return response.data[0].url
        except Exception as e:
            if verbose:
                logger.info(f"[Attempt {attempt + 1}/{retries}] Image generation failed: {e}")
    return None


def download_image(image_url):
    if power_debug_mode == True:
        logger.info("[write_news.py] - Downloading image...")

    r = requests.get(image_url)
    r.raise_for_status()
    with open(os.path.join(base_dir,"featured_image.jpg"), "wb") as f:
        f.write(r.content)

def crop_to_size(path):
    image = Image.open(path)
    
    # Define crop area
    left = 0
    top = (1024 - 537) // 2  # Crop equally from top and bottom
    right = 1024
    bottom = top + 537
    
    # Crop the image
    cropped_image = image.crop((left, top, right, bottom))
    cropped_image.save(os.path.join(base_dir,"featured_image.jpg"))

    return None        