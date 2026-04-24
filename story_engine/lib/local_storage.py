"""Local file-based storage replacing Firebase Storage.

All media (images, video, audio) is stored under output/ as flat files.
"""
import os
import io
from pathlib import Path
from PIL import Image


OUTPUT_DIR = Path(os.environ.get("VALMIKI_OUTPUT_DIR", "output"))


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def download_image_from_storage(path: str) -> Image.Image:
    """Load an image from local output directory."""
    local_path = OUTPUT_DIR / path
    if not local_path.exists():
        raise FileNotFoundError(f"Image not found: {local_path}")
    return Image.open(local_path)


def upload_image(image: Image.Image, path: str, **kwargs) -> str:
    """Save an image to local output directory. Returns the local path."""
    local_path = OUTPUT_DIR / path
    _ensure_dir(local_path)
    image.save(local_path)
    return str(local_path)


def upload_video(video_data: bytes, path: str, **kwargs) -> str:
    """Save video bytes to local output directory. Returns the local path."""
    local_path = OUTPUT_DIR / path
    _ensure_dir(local_path)
    local_path.write_bytes(video_data)
    return str(local_path)


def get_signed_url(path: str, **kwargs) -> str:
    """Return a file:// URL for local files."""
    local_path = OUTPUT_DIR / path
    return f"file://{local_path.resolve()}"


def download_image(url: str) -> Image.Image:
    """Download image from URL or load from local path."""
    if url.startswith("file://"):
        return Image.open(url[7:])
    if os.path.exists(url):
        return Image.open(url)
    # Fall back to HTTP download
    import requests
    resp = requests.get(url)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content))
