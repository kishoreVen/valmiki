
"""Image utilities for story engine.

This module provides image downloading capabilities that work in standalone contexts
(like playgrounds) without requiring Firebase dependencies.
"""

import base64
import io
import logging
from typing import Optional

import requests
from PIL import Image

# Optional import for Google Cloud Storage
try:
    from google.cloud import storage as gcs_storage
    HAS_GCS = True
except ImportError:
    gcs_storage = None
    HAS_GCS = False

# Optional import for Firebase Storage
try:
    from story_engine.lib.local_storage import download_image_from_storage
    HAS_FIREBASE = True
except ImportError:
    download_image_from_storage = None
    HAS_FIREBASE = False

logger = logging.getLogger(__name__)


def download_image(image_source: str, max_retries: int = 2) -> Image.Image:
    """Download image from various sources and return as PIL Image.

    Supports:
    - gs:// URLs (Google Cloud Storage)
    - Firebase Storage paths (e.g., 'story_generation/...')
    - http:// and https:// URLs
    - data: URLs (base64 encoded)
    - Local file paths

    Retries on OSError (truncated images) for network-based sources.

    Args:
        image_source: URL, gs:// path, Firebase Storage path, data URL, or local file path
        max_retries: Number of retries on OSError for network sources. Default 2.

    Returns:
        PIL Image object

    Raises:
        ValueError: If image cannot be downloaded or processed after all retries
    """
    # Network-based sources that can benefit from retry on truncation
    is_network_source = (
        image_source.startswith('gs://')
        or image_source.startswith('story_generation/')
        or image_source.startswith('http://')
        or image_source.startswith('https://')
    )
    attempts = (max_retries + 1) if is_network_source else 1

    for attempt in range(attempts):
        try:
            if image_source.startswith('gs://'):
                return _download_from_gcs(image_source)
            elif image_source.startswith('story_generation/'):
                return _download_from_firebase_storage(image_source)
            elif image_source.startswith('data:'):
                return _decode_data_url(image_source)
            elif image_source.startswith('http://') or image_source.startswith('https://'):
                return _download_from_http(image_source)
            elif _looks_like_base64(image_source):
                return _decode_raw_base64(image_source)
            else:
                return _load_from_file(image_source)

        except OSError as e:
            if attempt < attempts - 1:
                logger.warning(
                    f"Retry {attempt + 1}/{max_retries} for {image_source[:100]}: {e}"
                )
                continue
            # Final attempt failed
            logger.error(f"Failed to download image from {image_source[:100]} after {attempts} attempts: {e}")
            raise ValueError(f"Failed to download or process image after {attempts} attempts: {e}")

        except Exception as e:
            logger.error(f"Failed to download image from {image_source[:100]}: {e}")
            raise ValueError(f"Failed to download or process image: {e}")


def _download_from_gcs(gs_url: str) -> Image.Image:
    """Download image from Google Cloud Storage.

    Args:
        gs_url: URL in format gs://bucket-name/path/to/file

    Returns:
        PIL Image object

    Raises:
        ValueError: If GCS library not available or download fails
    """
    if not HAS_GCS:
        raise ValueError(
            "google-cloud-storage package not installed. "
            "Install with: pip install google-cloud-storage"
        )

    # Parse gs:// URL
    parts = gs_url[5:].split('/', 1)
    bucket_name = parts[0]
    file_path = parts[1] if len(parts) > 1 else ''

    # Download from GCS
    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(file_path)

    image_bytes = blob.download_as_bytes()
    image = Image.open(io.BytesIO(image_bytes))

    return _convert_image_mode(image)


def _download_from_firebase_storage(storage_path: str) -> Image.Image:
    """Download image from Firebase Storage path.

    Args:
        storage_path: Path in Firebase Storage bucket (e.g., 'story_generation/user/img.png')

    Returns:
        PIL Image object

    Raises:
        ValueError: If Firebase Storage library not available or download fails
    """
    if not HAS_FIREBASE:
        raise ValueError(
            "Firebase Storage not available. "
            "Make sure story_engine.lib.local_storage is importable."
        )

    image_bytes = download_image_from_storage(storage_path)
    image = Image.open(io.BytesIO(image_bytes))

    return _convert_image_mode(image)


def _download_from_http(url: str) -> Image.Image:
    """Download image from HTTP(S) URL.

    Args:
        url: HTTP or HTTPS URL

    Returns:
        PIL Image object
    """
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content))

    return _convert_image_mode(image)


def _decode_data_url(data_url: str) -> Image.Image:
    """Decode base64 data URL to image.

    Args:
        data_url: Data URL in format data:image/...;base64,...

    Returns:
        PIL Image object
    """
    # Extract base64 data after the comma
    _, data = data_url.split(',', 1)
    image_bytes = base64.b64decode(data)
    image = Image.open(io.BytesIO(image_bytes))

    return _convert_image_mode(image)


def _looks_like_base64(s: str) -> bool:
    """Check if a string looks like raw base64-encoded image data."""
    # JPEG base64 starts with /9j/, PNG with iVBOR, GIF with R0lGO, WebP with UklGR
    if s[:4] in ('/9j/', 'iVBO', 'R0lG', 'UklG'):
        return True
    # Fallback: long string with only base64 chars and no path separators
    if len(s) > 200 and '/' not in s[:20]:
        try:
            base64.b64decode(s[:64], validate=True)
            return True
        except Exception:
            pass
    return False


def _decode_raw_base64(data: str) -> Image.Image:
    """Decode a raw base64 string (no data: prefix) to image."""
    image_bytes = base64.b64decode(data)
    image = Image.open(io.BytesIO(image_bytes))
    return _convert_image_mode(image)


def _load_from_file(file_path: str) -> Image.Image:
    """Load image from local file path.

    Args:
        file_path: Local filesystem path to image

    Returns:
        PIL Image object
    """
    image = Image.open(file_path)

    return _convert_image_mode(image)


def _convert_image_mode(image: Image.Image) -> Image.Image:
    """Convert image to appropriate mode for processing.

    For WebP and PNG images with alpha channel, convert to RGBA.
    For other formats, convert to RGB.
    Also preserves the original format info.

    Forces full pixel decode via image.load() to catch truncated images
    early rather than letting them fail silently downstream.

    Args:
        image: PIL Image to convert

    Returns:
        Converted PIL Image
    """
    original_format = image.format

    # Force full pixel decode to catch truncated images early.
    # Image.open() is lazy — truncation errors only surface when pixels are accessed.
    image.load()

    if image.mode in ('RGBA', 'LA', 'P') and image.format in ('WEBP', 'PNG'):
        converted_image = image.convert('RGBA')
    else:
        converted_image = image.convert('RGB')

    # Preserve format information
    converted_image.format = original_format
    return converted_image


def image_to_base64(image: Image.Image, include_data_uri_prefix: bool = False) -> str:
    """Convert PIL Image to base64 string.

    This is a convenience re-export from story_engine.lib.model_router.utils for use in
    contexts where we don't want to import from story_engine.lib.model_router.

    Args:
        image: PIL Image to convert
        include_data_uri_prefix: If True, prepend data URI prefix for web compatibility

    Returns:
        Base64 encoded string, optionally with data URI prefix
    """
    from story_engine.lib.model_router.utils import image_to_base64 as _image_to_base64
    return _image_to_base64(image, include_data_uri_prefix)
