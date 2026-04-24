
"""Video utilities for story engine.

Provides frame extraction from video bytes using ffmpeg subprocess.
"""

import io
import logging
import os
import subprocess
import tempfile

from PIL import Image

logger = logging.getLogger(__name__)


def extract_last_frame(video_bytes: bytes) -> Image.Image:
    """Extract the last frame from MP4 video bytes.

    Writes bytes to a temp file, uses ffmpeg to seek to the last frame,
    and returns it as a PIL Image.

    Args:
        video_bytes: Raw video file bytes (e.g. MP4).

    Returns:
        PIL Image of the last frame.

    Raises:
        ValueError: If video_bytes is empty or frame extraction fails.
    """
    if not video_bytes:
        raise ValueError("video_bytes is empty")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
        tmp_video.write(video_bytes)
        tmp_video_path = tmp_video.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_frame:
            tmp_frame_path = tmp_frame.name

        try:
            # sseof seeks from the end; -1 starts 1 second before end
            # -update 1 keeps overwriting so we end up with the last frame
            cmd = [
                "ffmpeg", "-y",
                "-sseof", "-1",
                "-i", tmp_video_path,
                "-update", "1",
                "-q:v", "2",
                tmp_frame_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not os.path.exists(tmp_frame_path):
                raise ValueError(
                    f"ffmpeg failed (code {result.returncode}): "
                    f"{result.stderr.decode(errors='replace')[-200:]}"
                )

            image = Image.open(tmp_frame_path).copy()
            return image
        finally:
            if os.path.exists(tmp_frame_path):
                os.unlink(tmp_frame_path)
    finally:
        os.unlink(tmp_video_path)


def extract_frame_at(video_bytes: bytes, time_seconds: float) -> Image.Image:
    """Extract a frame at a specific timestamp from video bytes.

    Args:
        video_bytes: Raw video file bytes (e.g. MP4).
        time_seconds: Timestamp in seconds to extract the frame at.

    Returns:
        PIL Image of the requested frame.

    Raises:
        ValueError: If video_bytes is empty or frame extraction fails.
    """
    if not video_bytes:
        raise ValueError("video_bytes is empty")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
        tmp_video.write(video_bytes)
        tmp_video_path = tmp_video.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_frame:
            tmp_frame_path = tmp_frame.name

        try:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(time_seconds),
                "-i", tmp_video_path,
                "-frames:v", "1",
                "-q:v", "2",
                tmp_frame_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not os.path.exists(tmp_frame_path):
                raise ValueError(
                    f"ffmpeg failed (code {result.returncode}): "
                    f"{result.stderr.decode(errors='replace')[-200:]}"
                )

            image = Image.open(tmp_frame_path).copy()
            return image
        finally:
            if os.path.exists(tmp_frame_path):
                os.unlink(tmp_frame_path)
    finally:
        os.unlink(tmp_video_path)
