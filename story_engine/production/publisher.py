
"""
Publisher module for generating device-specific aspect ratio images.

The illustration pipeline produces images at iPad 4:3 aspect ratio directly.
This module generates the iPhone (16:9) version via Gemini image-to-image outpainting.
"""

import base64
from dataclasses import dataclass, replace
import io
import logging

from PIL import Image

from story_engine.lib.model_router.model_interface import ImageGenQuery, Capability
from story_engine.lib.model_router.router import ModelRouter
from story_engine.lib.model_router.retry import RetryConfig

from story_engine.production.data_operators import (
    IllustratedScriptNode,
    PublishedPageOutput,
    DEVICE_LAYOUTS,
)

from story_engine.lib.local_storage import download_image_from_storage


logger = logging.getLogger(__name__)


def _resolve_image(img: str | Image.Image) -> Image.Image:
    """Resolve an image to PIL Image, downloading from storage if needed.

    Args:
        img: PIL Image, base64 string, Firebase Storage path, or HTTP(S) URL

    Returns:
        PIL Image
    """
    if isinstance(img, Image.Image):
        return img

    # Check if this is a Firebase Storage path
    if isinstance(img, str) and img.startswith("story_generation/"):
        img_bytes = download_image_from_storage(img)
        return Image.open(io.BytesIO(img_bytes))

    # Check if this is an HTTP(S) URL (e.g. Firebase Storage download URL)
    if isinstance(img, str) and (img.startswith("http://") or img.startswith("https://")):
        import requests
        resp = requests.get(img, timeout=30)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content))

    # Handle base64 encoded images
    if isinstance(img, str):
        import base64

        # Try to decode as base64
        try:
            img_bytes = base64.b64decode(img)
            return Image.open(io.BytesIO(img_bytes))
        except Exception:
            pass

    raise ValueError(
        f"Unexpected image type: {type(img)}, value starts with: {str(img)[:50]}"
    )


@dataclass
class PublisherConfig:
    """Configuration for the Publisher."""

    illustration_style: str  # One of: abstract, cartoon, line_drawing, manga, moody, realistic, vintage, whimsical, wimmelbuch
    interface_type: str = "gemini_pro3_image"

    retry_config: RetryConfig | None = None


class Publisher:
    """Generates device-specific aspect ratio images using Gemini image-to-image."""

    def __init__(self, config: PublisherConfig) -> None:
        """Initialize the Publisher with configuration.

        Args:
            config: PublisherConfig containing interface type and illustration style
        """
        self.config = config
        self.router = ModelRouter(retry_config=self.config.retry_config)

    def update_config(self, **kwargs) -> None:
        """Update specific fields of the publisher configuration.

        Args:
            **kwargs: Fields to update in the config
        """
        self.config = replace(self.config, **kwargs)

    def _outpaint_for_device(
        self,
        source_image: Image.Image,
        target_width: int,
        target_height: int,
        aspect_ratio: str,
    ) -> str:
        """Use Gemini to extend image to target aspect ratio.

        Args:
            source_image: The source 1:1 illustration
            target_width: Target width in pixels
            target_height: Target height in pixels
            aspect_ratio: Human-readable aspect ratio (e.g., "4:3", "16:9")

        Returns:
            Base64 encoded image at target aspect ratio
        """
        prompt = f"""Extend this illustration to a {aspect_ratio} aspect ratio.
Preserve the art style.
Seamlessly extend the background and scene elements.
Keep the main subject centered and fully visible.
Do not crop or distort the original content."""

        query = ImageGenQuery(
            query_text=prompt,
            images=source_image,
            image_resolution=(target_width, target_height),
            repetitions=2,
        )

        response = self.router.get_response(
            query, Capability.IMAGE_GEN, self.config.interface_type
        )
        return response["images"][0]

    def publish_title(
        self,
        lettered_title_image: str,
    ) -> tuple[str, str]:
        """Generate device-specific title images from the lettered title.

        iPad: Re-encodes the lettered title as-is (already 4:3).
        iPhone: Outpaints to 16:9 via Gemini.

        Args:
            lettered_title_image: Base64 encoded lettered title image (4:3)

        Returns:
            Tuple of (ipad_image_base64, iphone_image_base64)
        """
        source_image = _resolve_image(lettered_title_image)

        # iPad: re-encode as base64
        buffer = io.BytesIO()
        source_image.save(buffer, format="PNG")
        ipad_image = base64.b64encode(buffer.getvalue()).decode()

        # iPhone: outpaint to target aspect ratio
        iphone_layout = DEVICE_LAYOUTS["iphone"]
        logger.info(f"Title page: Generating iPhone image ({iphone_layout['str_ratio']})")
        iphone_image = self._outpaint_for_device(
            source_image,
            iphone_layout["width"],
            iphone_layout["height"],
            iphone_layout["str_ratio"],
        )

        return ipad_image, iphone_image

    def publish_page(
        self,
        illustrated_node: IllustratedScriptNode,
    ) -> PublishedPageOutput:
        """Generate device-specific aspect ratio images for an illustrated page.

        The source illustration is already at iPad 4:3 aspect ratio, so it is
        used directly as the iPad image. Only the iPhone (16:9) version is
        generated via Gemini outpainting.

        Args:
            illustrated_node: The illustrated script node with 4:3 image

        Returns:
            PublishedPageOutput with device-specific images
        """
        # Use lettered image if available, then critic-revised, styled, original
        source_url = (
            illustrated_node.lettered_image_url
            or illustrated_node.critic_revised_image_url
            or illustrated_node.styled_image_url
            or illustrated_node.image_url
        )

        if not source_url:
            logger.warning(
                f"Page {illustrated_node.node.page}: No source image available"
            )
            return PublishedPageOutput(
                illustrated_node=illustrated_node,
                status="error",
                error="No source image available",
            )

        logger.info(
            f"Page {illustrated_node.node.page}: Generating device-specific images"
        )

        # Resolve the source image to PIL (needed for both iPad and iPhone)
        source_image = _resolve_image(source_url)

        # iPad image: encode resolved image as base64 so it gets its own
        # Firebase upload path (published/N_ipad.png) instead of being a
        # stale URL reference back to pages/N_critic.png.
        buffer = io.BytesIO()
        source_image.save(buffer, format="PNG")
        ipad_image = base64.b64encode(buffer.getvalue()).decode()

        # Generate iPhone image via outpainting
        iphone_layout = DEVICE_LAYOUTS["iphone"]
        logger.info(
            f"Page {illustrated_node.node.page}: Generating iPhone image ({iphone_layout['str_ratio']})"
        )
        iphone_image = self._outpaint_for_device(
            source_image,
            iphone_layout["width"],
            iphone_layout["height"],
            iphone_layout["str_ratio"],
        )

        return PublishedPageOutput(
            illustrated_node=illustrated_node,
            status="completed",
            ipad_image=ipad_image,
            iphone_image=iphone_image,
        )
