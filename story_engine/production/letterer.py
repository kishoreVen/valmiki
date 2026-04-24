
"""
Letterer module for adding speech bubbles and narrator captions to illustrated pages.

Uses Gemini image generation to render dialog and narrator text onto existing
illustrations as a post-processing step before publishing.
"""

import base64
import io
import logging
from dataclasses import dataclass, replace

from PIL import Image

from story_engine.lib.model_router.model_interface import ImageGenQuery, Capability
from story_engine.lib.model_router.router import ModelRouter
from story_engine.lib.model_router.retry import RetryConfig

from story_engine.production.data_operators import IllustratedScriptNode
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

    if isinstance(img, str) and img.startswith("story_generation/"):
        img_bytes = download_image_from_storage(img)
        return Image.open(io.BytesIO(img_bytes))

    if isinstance(img, str) and (img.startswith("http://") or img.startswith("https://")):
        import requests
        resp = requests.get(img, timeout=30)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content))

    if isinstance(img, str):
        try:
            img_bytes = base64.b64decode(img)
            return Image.open(io.BytesIO(img_bytes))
        except Exception:
            pass

    raise ValueError(
        f"Unexpected image type: {type(img)}, value starts with: {str(img)[:50]}"
    )


@dataclass
class LettererConfig:
    """Configuration for the Letterer."""

    illustration_style: str
    interface_type: str = "gemini_pro3_image"
    retry_config: RetryConfig | None = None


class Letterer:
    """Adds speech bubbles and narrator captions to illustrated pages using Gemini."""

    def __init__(self, config: LettererConfig) -> None:
        self.config = config
        self.router = ModelRouter(retry_config=self.config.retry_config)

    def update_config(self, **kwargs) -> None:
        self.config = replace(self.config, **kwargs)

    def has_lettering_content(self, illustrated_node: IllustratedScriptNode) -> bool:
        """Check if a page has dialog or narrator text that needs lettering."""
        node = illustrated_node.node
        has_dialog = node.dialog is not None and len(node.dialog) > 0
        has_narrator = node.narrator is not None and len(node.narrator.strip()) > 0
        return has_dialog or has_narrator

    def letter_page(self, illustrated_node: IllustratedScriptNode) -> tuple[str, str]:
        """Add speech bubbles and narrator captions to an illustrated page.

        Args:
            illustrated_node: The illustrated page to add lettering to

        Returns:
            Tuple of (base64 encoded image, prompt used for generation)
        """
        node = illustrated_node.node

        # Use best available image: critic-revised > styled > original
        source_url = (
            illustrated_node.critic_revised_image_url
            or illustrated_node.styled_image_url
            or illustrated_node.image_url
        )
        if not source_url:
            raise ValueError(f"Page {node.page}: No source image available for lettering")

        source_image = _resolve_image(source_url)

        # Build the lettering prompt
        prompt = self._build_prompt(node.dialog, node.narrator)

        query = ImageGenQuery(
            query_text=prompt,
            images=source_image,
            image_resolution=(source_image.width, source_image.height),
            repetitions=2,
        )

        response = self.router.get_response(
            query, Capability.IMAGE_GEN, self.config.interface_type
        )
        return response["images"][0], prompt

    def letter_title_page(
        self,
        title_shot_image: str,
        title: str,
    ) -> tuple[str, str]:
        """Add stylized title text to the title shot image.

        Also enhances character appeal in the image.

        Args:
            title_shot_image: Base64 encoded (or URL) title shot image
            title: The story title text to overlay

        Returns:
            Tuple of (base64 encoded image, prompt used for generation)
        """
        source_image = _resolve_image(title_shot_image)

        prompt = self._build_title_prompt(title)

        query = ImageGenQuery(
            query_text=prompt,
            images=source_image,
            image_resolution=(source_image.width, source_image.height),
            repetitions=2,
        )

        response = self.router.get_response(
            query, Capability.IMAGE_GEN, self.config.interface_type
        )
        return response["images"][0], prompt

    def _build_title_prompt(self, title: str) -> str:
        """Build the Gemini prompt for adding a stylized title to the title shot."""
        parts = [
            f'Add the story title "{title}" to this illustration as a stylized graphic title.',
            "",
            "TITLE STYLING:",
            "- Render the title as a prominent, beautifully designed typographic element",
            "- The title should be large, centered, and immediately readable",
            "- Use a font style that matches the illustration's art direction",
            "- Add subtle effects like drop shadow, glow, or outline to ensure legibility over the background",
            "",
            "RULES:",
            "- Preserve the overall composition and background of the illustration",
            "- The title should not obscure characters' faces",
            "- CRITICAL: Place the title in the lower 70% of the image only. The top 30% is reserved and must remain clear.",
            "- Do NOT add any text beyond the story title",
            "- Do NOT add subtitles, author names, or other text elements",
        ]
        prompt = "\n".join(parts)
        logger.info(f"Letterer title prompt: {prompt}")
        return prompt

    def _build_prompt(
        self,
        dialog: dict[str, str] | None,
        narrator: str | None,
    ) -> str:
        """Build the Gemini prompt for adding lettering to an illustration."""
        has_dialog = dialog is not None and len(dialog) > 0
        has_narrator = narrator is not None and len(narrator.strip()) > 0

        # Describe exactly what to add based on what's present
        if has_dialog and has_narrator:
            element_desc = "speech bubbles and a narrator caption box"
        elif has_dialog:
            element_desc = "speech bubbles"
        else:
            element_desc = "a narrator caption box"

        parts = [
            f"Add {element_desc} to this illustration. "
            "Preserve the existing illustration EXACTLY — do not change any art, colors, or composition. "
            "Only ADD the following text elements on top:"
        ]

        if has_dialog:
            parts.append("\nSPEECH BUBBLES:")
            for character_name, line in dialog.items():
                parts.append(
                    f'- {character_name} says: "{line}" '
                    f"(white speech bubble with black outline, tail pointing toward {character_name})"
                )

        if has_narrator:
            parts.append(
                f'\nNARRATOR CAPTION BOX:\n'
                f'- Text: "{narrator}"\n'
                f'- Style: rectangular semi-transparent box with clean text'
            )

        parts.append(
            "\nPOSITIONING RULES:"
            "\n- CRITICAL: ALL text elements (bubbles and captions) MUST be placed in the lower 70% of the image. The top 30% is reserved and must remain completely clear of any added text or UI elements."
            "\n- Do NOT place bubbles or captions over existing text in the image"
            "\n- Do NOT obscure characters' faces or other critical foreground content"
            "\n- Prefer empty or low-detail areas (sky, margins, open background) for placement within the lower 70%"
            "\n- Narrator caption boxes should be placed at the bottom edge of the image"
        )

        parts.append(
            "\nSTYLE RULES:"
            "\n- White bubbles with black outlines"
            "\n- Clean, rounded, legible font"
            "\n- Text must be fully readable"
            "\n- Do NOT alter the underlying illustration in any way"
            "\n- Do NOT add any text elements beyond what is listed above"
        )

        prompt = "\n".join(parts)
        logger.info(f"Letterer prompt: {prompt}")
        return prompt
