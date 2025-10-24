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

WP_USERNAME = "admin_z4jlswba"  # user tied to the Application Password
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

def _force_set_language(post_id: int, slug: str) -> bool:
    """
    Force-assign the post language after creation via Polylang.
    Works even if the create call ignored ?lang=...
    """
    try:
        url = f"{WP_POSTS_URL}/{post_id}"
        # POST with only query params; no JSON body needed
        r = requests.post(url, auth=auth, params={"lang": slug}, timeout=30)
        if r.status_code in (200, 201):
            logger.info("Language set → post %s → %s", post_id, slug)
            return True
        logger.warning("Failed to set language for %s → %s | %s %s",
                       post_id, slug, r.status_code, r.text[:200])
    except Exception as exc:
        logger.warning("Exception while setting language: %s", exc)
    return False

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

# --- Polylang helpers ---

def _polylang_rest_available() -> bool:
    """Best-effort check whether Polylang REST endpoints are available."""
    try:
        url = f"{WP_DOMAIN.rstrip('/')}/wp-json/pll/v1/languages"
        resp = requests.get(url, auth=auth, timeout=15)
        if resp.status_code == 200:
            logger.info("[poster.py] Polylang REST detected.")
            return True
        logger.info("[poster.py] Polylang REST not detected (status %s).", resp.status_code)
    except Exception as exc:
        logger.info("[poster.py] Polylang REST check failed: %s", exc)
    return False


def _normalize_lang_code(language: Optional[str]) -> Optional[str]:
    """Accepts 'DE', 'de', 'De' etc. Returns lowercase 2–5 char code or None."""
    if not language:
        return None
    code = language.strip().lower()
    # allow simple codes like 'de', 'ru', 'fr' or longer like 'zh-cn'
    return code if 2 <= len(code) <= 5 else None

def post_to_wordpress(
    title: str,
    content: str,
    *,
    status: str = "publish",
    featured_image_id: Optional[int] = None,
    tags: Optional[Iterable[Union[str, int]]] = None,
    tag_ids: Optional[Iterable[int]] = None,
    categories: Optional[Iterable[Union[str, int]]] = None,
    category_ids: Optional[Iterable[int]] = None,
    # NEW ↓↓↓
    language: Optional[str] = None,
    translations: Optional[dict[str, int]] = None,
) -> Optional[dict]:
    """
    Create a WordPress post.

    Polylang:
      - If `language` is provided (e.g. "DE", "de"), and Polylang REST is available,
        the post is created with that language via the `lang` query param.
      - If `translations` is provided as a mapping { "en": 123, "de": 456, ... },
        we PATCH the created post with `translations[...]` params to link siblings.
        (Requires Polylang REST features; if unavailable, we log a warning.)

    Returns the created post JSON dict on success, otherwise None.
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

    # --- Categories (names and/or IDs) ---
    merged_cats: List[Union[str, int]] = []
    if categories:
        merged_cats.extend(categories)
    if category_ids:
        merged_cats.extend(category_ids)
    resolved_cat_ids = resolve_terms(merged_cats, taxonomy="categories")
    if resolved_cat_ids:
        payload["categories"] = resolved_cat_ids

    # --- Build URL (optionally with Polylang language) ---
    url = WP_POSTS_URL
    lang_code = _normalize_lang_code(language)
    params = {}
    if lang_code:
        # Always try to set language on create
        params["lang"] = lang_code

    # --- Create the post ---
    try:
        resp = requests.post(url, auth=auth, json=payload, params=params or None, timeout=60)
    except Exception as exc:
        logger.exception("Post creation request failed: %s", exc)
        return None

    if resp.status_code != 201:
        logger.error("Failed to create post. Status=%s, Body=%s", resp.status_code, resp.text)
        if lang_code and not pll_ok:
            logger.warning(
                "Note: Polylang REST not detected; cannot assign language via API. "
                "Post created without explicit Polylang language."
            )
        return None

    data = resp.json()
    post_id = data.get("id")
    logger.info("Article posted. Post ID=%s, Link=%s", post_id, data.get("link"))
    # Safety net: if a language was requested, force-set it post-creation
    if lang_code:
        _force_set_language(int(post_id), lang_code)

    # --- Link translations (optional) ---

    if translations and isinstance(translations, dict):
        try:
            # Build query params like translations[en]=123
            link_params = {"lang": lang_code} if lang_code else {}
            for code, sibling_id in translations.items():
                if not sibling_id:
                    continue
                key = f"translations[{str(code).strip().lower()}]"
                link_params[key] = int(sibling_id)

            link_url = f"{WP_POSTS_URL}/{post_id}"
            link_resp = requests.post(link_url, auth=auth, params=link_params, timeout=60)
            if link_resp.status_code in (200, 201):
                data = link_resp.json()
                logger.info("Linked translations for Post ID=%s → %s", post_id, data.get("translations"))
            else:
                logger.warning(
                    "Failed to link translations. Status=%s Body=%s",
                    link_resp.status_code, link_resp.text,
                )
        except Exception as exc:
            logger.warning("Exception while linking translations: %s", exc)

    return data
