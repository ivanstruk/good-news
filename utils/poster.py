# utils/poster.py
from __future__ import annotations

import os
import mimetypes
from pathlib import Path
from typing import Iterable, Optional

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from utils.logger import logger  # logger.py lives in the same folder

# === Paths === (your preferred style)
base_dir = Path(__file__).resolve().parent.parent  # project root
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# -------- API Configurations --------
# WordPress (domain + app password)
logger.info("[poster.py] - Connecting to WordPress")

WP_DOMAIN = os.getenv("domain")  # e.g. https://example.com
if not WP_DOMAIN:
    logger.warning("No 'domain' set in .env. WordPress requests will fail.")

WP_API_BASE = f"{WP_DOMAIN.rstrip('/')}/wp-json/wp/v2"
WP_POSTS_URL = f"{WP_API_BASE}/posts"
WP_MEDIA_URL = f"{WP_API_BASE}/media"

WP_USERNAME = "admin"  # user tied to the Application Password
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD") or ""
if not WP_APP_PASSWORD:
    logger.warning("WP_APP_PASSWORD not set in .env. Authentication will fail.")

auth = HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)


def upload_featured_image(image_path: str) -> Optional[int]:
    """
    Upload an image file to the WordPress Media Library.

    Returns:
        media_id (int) on success, or None on failure.
    """
    if not os.path.isfile(image_path):
        logger.error("Featured image not found at path: %s", image_path)
        return None

    filename = os.path.basename(image_path)
    content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    try:
        with open(image_path, "rb") as f:
            files = {"file": (filename, f, content_type)}
            resp = requests.post(WP_MEDIA_URL, auth=auth, headers=headers, files=files, timeout=60)
    except Exception as exc:
        logger.exception("Image upload request failed: %s", exc)
        return None

    if resp.status_code in (200, 201):
        try:
            media_id = int(resp.json().get("id"))
        except Exception:
            media_id = None
        logger.info("Uploaded featured image. Media ID=%s", media_id)
        return media_id

    logger.error("Image upload failed. Status=%s, Body=%s", resp.status_code, resp.text)
    return None


def post_to_wordpress(
    title: str,
    content: str,
    *,
    status: str = "publish",
    featured_image_id: Optional[int] = None,
    tag_ids: Optional[Iterable[int]] = None,
    category_ids: Optional[Iterable[int]] = None,
) -> Optional[dict]:
    """
    Create a WordPress post.

    Args:
        title: Post title.
        content: HTML content.
        status: 'draft', 'publish', etc. Default 'publish'.
        featured_image_id: Media ID returned by upload_featured_image().
        tag_ids: Iterable of existing tag IDs (integers). Optional.
        category_ids: Iterable of existing category IDs (integers). Optional.

    Returns:
        The created post JSON dict on success (201), else None.
    """
    payload = {
        "title": title,
        "content": content,
        "status": status,
    }

    if featured_image_id:
        payload["featured_media"] = int(featured_image_id)

    if tag_ids:
        try:
            payload["tags"] = [int(t) for t in tag_ids]
        except Exception:
            logger.warning("tag_ids must be integers. Skipping tags.")
    if category_ids:
        try:
            payload["categories"] = [int(c) for c in category_ids]
        except Exception:
            logger.warning("category_ids must be integers. Skipping categories.")

    try:
        resp = requests.post(WP_POSTS_URL, auth=auth, json=payload, timeout=60)
    except Exception as exc:
        logger.exception("Post creation request failed: %s", exc)
        return None

    if resp.status_code == 201:
        data = resp.json()
        logger.info("Article posted. Post ID=%s, Link=%s", data.get("id"), data.get("link"))
        return data

    logger.error("Failed to create post. Status=%s, Body=%s", resp.status_code, resp.text)
    return None
