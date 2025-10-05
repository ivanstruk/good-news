# utils/poster.py
from __future__ import annotations

import os
import mimetypes
from pathlib import Path
from typing import Iterable, Optional, Union, List

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

def get_or_create_term(name: str, taxonomy: str) -> int:
    """
    Reuse your existing function. Added small niceties: timeout and exact match.
    """
    url = f"{WP_API_BASE}/{taxonomy}"

    # Try to find it
    try:
        response = requests.get(url, params={"search": name}, auth=auth, timeout=30)
    except Exception as exc:
        logger.warning("Lookup failed for %s '%s': %s", taxonomy, name, exc)
        response = None

    if response and response.status_code == 200:
        data = response.json() or []
        for item in data:
            if str(item.get("name", "")).lower() == name.lower():
                return int(item["id"])

    # If not found, try to create it
    try:
        response = requests.post(url, json={"name": name}, auth=auth, timeout=30)
    except Exception as exc:
        logger.info("[poster.py] - Failed to create %s '%s': %s", taxonomy[:-1], name, exc)
        raise

    if response.status_code in (200, 201):
        return int(response.json()["id"])

    logger.info("[poster.py] - Failed to create %s '%s': %s", taxonomy[:-1], name, response.text)
    raise Exception(f"Failed to create {taxonomy[:-1]} '{name}': {response.text}")


def resolve_terms(
    terms: Optional[Iterable[Union[str, int]]],
    taxonomy: str,
) -> List[int]:
    """
    Convert a mix of names/IDs into IDs, creating missing names via get_or_create_term().
    taxonomy: 'tags' or 'categories'
    """
    if not terms:
        return []

    resolved: List[int] = []
    for term in terms:
        if term is None:
            continue
        if isinstance(term, int):
            resolved.append(term)
        elif isinstance(term, str) and term.strip():
            try:
                term_id = get_or_create_term(term.strip(), taxonomy=taxonomy)
                resolved.append(int(term_id))
            except Exception as exc:
                logger.warning("Skipping %s '%s' due to error: %s", taxonomy[:-1], term, exc)
        else:
            logger.warning("Unsupported %s entry: %r", taxonomy[:-1], term)

    # de-duplicate while preserving order
    seen = set()
    unique_ids: List[int] = []
    for tid in resolved:
        if tid not in seen:
            seen.add(tid)
            unique_ids.append(tid)
    return unique_ids

def post_to_wordpress(
    title: str,
    content: str,
    *,
    status: str = "publish",
    featured_image_id: Optional[int] = None,
    # NEW: accept tag NAMES (strings). You can still pass integers if you want.
    tags: Optional[Iterable[Union[str, int]]] = None,
    # Back-compat: you can still pass raw tag IDs if you already have them.
    tag_ids: Optional[Iterable[int]] = None,
    # You can also pass category names/ids the same way if you want (optional).
    categories: Optional[Iterable[Union[str, int]]] = None,
    category_ids: Optional[Iterable[int]] = None,
) -> Optional[dict]:
    """
    Create a WordPress post. Accepts tags as names (strings) or IDs.
    If both tags and tag_ids are supplied, they are merged and de-duplicated.
    Likewise for categories and category_ids.
    """
    payload = {
        "title": title,
        "content": content,
        "status": status,
    }

    if featured_image_id:
        payload["featured_media"] = int(featured_image_id)

    # --- Tags (names and/or IDs) ---
    merged_tags: List[Union[str, int]] = []
    if tags:
        merged_tags.extend(tags)
    if tag_ids:
        merged_tags.extend(tag_ids)

    resolved_tag_ids = resolve_terms(merged_tags, taxonomy="tags")
    if resolved_tag_ids:
        payload["tags"] = resolved_tag_ids

    # --- Categories (optional; supports names and/or IDs) ---
    merged_cats: List[Union[str, int]] = []
    if categories:
        merged_cats.extend(categories)
    if category_ids:
        merged_cats.extend(category_ids)

    resolved_cat_ids = resolve_terms(merged_cats, taxonomy="categories")
    if resolved_cat_ids:
        payload["categories"] = resolved_cat_ids

    # --- Create the post ---
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
