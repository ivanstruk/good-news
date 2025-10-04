


def upload_featured_image(image_path):
    filename = os.path.basename(image_path)
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type": "image/jpg"
    }

    with open(image_path, 'rb') as img:
        response = requests.post(
            f"{WP_API_BASE}/media",
            headers=headers,
            auth=auth,
            data=img
        )

    if response.status_code in [200, 201]:
        media_id = response.json().get("id")
        logger.info(f"[write_news.py] - ✅ Uploaded image. Media ID: {media_id}")
        return media_id
    else:
        logger.info(f"[write_news.py] - ❌ Image upload failed: {response.status_code}")
        logger.info(response.text)
        return None


