# utils/poster.py
from __future__ import annotations

import os
import mimetypes
from pathlib import Path
from typing import Iterable, Optional

import requests
from dotenv import load_dotenv
from utils.logger import logger  # logger.py lives in the same folder

# === Paths === (your preferred style)
base_dir = Path(__file__).resolve().parent.parent  # project root
dotenv_path = os.path.join(base_dir, ".env")
load_dotenv(dotenv_path)

# === Config from environment ===
WP_API_BASE = (os.getenv("WP_API_BASE") or "").rstrip("/")
WP_USER = os.getenv("WP_USER") or ""
WP_PASS = os.getenv("WP_PASS") or ""

if not WP_API_BASE:
    logger.warning("WP_API_BASE is not set. WordPress requests will fail.")
if not WP_USER or not WP_PASS:
    logger.warning("WP_USER / WP_PASS not set. Auth will fail.")

WP_POSTS_URL = f"{WP_API_BASE}/posts"
WP_MEDIA_URL = f"{WP_API_BASE}/media"


def _auth() -> requests.auth.HTTPBasicAuth:
    """Create HTTP Basic auth object."""
    return requests.auth.HTTPBasicAuth(WP_USER, WP_PASS)


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
    # Guess content type; fallback to jpeg if unknown
    content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    try:
        with open(image_path, "rb") as f:
            files = {"file": (filename, f, content_type)}
            resp = requests.post(WP_MEDIA_URL, auth=_auth(), headers=headers, files=files, timeout=60)
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
    Create a WordPress post (no taxonomy helper imports).

    Args:
        title: Post title.
        content: HTML content.
        status: 'draft', 'publish', etc. Default 'publish'.
        featured_image_id: Media ID returned by upload_featured_image().
        tag_ids: Iterable of existing tag IDs (integers). Optional.
        category_ids: Iterable of existing category IDs (integers). Optional.

    Returns:
        The created post JSON dict on success (201), else None.

    Notes:
        - This function assumes you already have numeric IDs for tags/categories.
          If you pass names instead of IDs, WordPress will reject the request.
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
        resp = requests.post(WP_POSTS_URL, auth=_auth(), json=payload, timeout=60)
    except Exception as exc:
        logger.exception("Post creation request failed: %s", exc)
        return None

    if resp.status_code == 201:
        data = resp.json()
        logger.info("Article posted. Post ID=%s, Link=%s", data.get("id"), data.get("link"))
        return data

    logger.error("Failed to create post. Status=%s, Body=%s", resp.status_code, resp.text)
    return None
