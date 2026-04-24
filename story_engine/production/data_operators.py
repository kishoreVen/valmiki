
# Centralized data classes for all model outputs in the story engine production pipeline.
# These dataclasses define the structure of data flowing between pipeline stages.

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Literal


# =============================================================================
# SHARED TYPES
# =============================================================================

# Checklist item priority levels
ChecklistPriority = Literal["P0", "P1", "P2"]  # P0=blocking, P1=important, P2=minor


# =============================================================================
# BASE CLASS
# =============================================================================


@dataclass
class JsonSerializable:
    """Base class providing JSON serialization for dataclasses."""

    def to_dict(self) -> Dict:
        """Convert this dataclass to a dictionary.

        Returns:
            Dictionary representation of the dataclass.
        """
        return asdict(self)

    def to_json(self, indent: int | None = None) -> str:
        """Serialize this dataclass to a JSON string.

        Args:
            indent: Optional indentation level for pretty printing.

        Returns:
            JSON string representation of the dataclass.
        """
        return json.dumps(self.to_dict(), indent=indent)

    def __str__(self) -> str:
        """Return JSON representation when converted to string."""
        return self.to_json()


# =============================================================================
# DIRECTOR OUTPUTS
# =============================================================================


@dataclass
class ConceptOutput(JsonSerializable):
    """Output from director.generate_concept() - the core concept without illustration."""

    title: str
    pitch: str
    title_shot: str
    illustration_style: str = ""  # Set by Director (random or explicit), not by LLM

    @staticmethod
    def schema() -> str:
        return """{
    "title": string, // A catchy title for the story
    "pitch": string, // A brief summary of the story concept describing the high level story idea.
    "title_shot": string, // A visual description of what the title screen should look like
}"""


@dataclass
class ConceptIllustratedOutput(JsonSerializable):
    """Output from director.generate_concept() with illustration data."""

    concept: ConceptOutput
    title_shot_prompt: str | None = None  # Styled image prompt
    title_shot_image: str | None = None  # Styled image (base64)
    lettered_title_image: str | None = None  # Title text overlaid (base64)
    lettered_title_prompt: str | None = None
    published_title_ipad_image: str | None = None  # 4:3 (base64)
    published_title_iphone_image: str | None = None  # 16:9 (base64)


@dataclass
class ProseOutput(JsonSerializable):
    """Output from author.generate_prose() - the full narrative prose of the story."""

    prose: str  # The complete story prose written in novel-like form

    @staticmethod
    def schema() -> str:
        return """{
    "prose": string // The complete story narrative written as prose. This is a novel-like writeup describing the full story from start to finish, including what happened, where, who was involved, and how events unfolded. This prose will guide the scripter when creating page-by-page scripts.
}"""


# =============================================================================
# PAGE OUTLINE OUTPUTS (Prose -> Script bridge)
# =============================================================================


@dataclass
class PageOutlineNode(JsonSerializable):
    """A single page in the page-by-page outline.

    Each page represents one visual moment / scene in the picture book.
    The page_description is a short prose summary of what happens on this page.
    """

    page: int  # 1-indexed page number
    page_description: str  # What happens on this page (2-4 sentences)

    @staticmethod
    def schema() -> str:
        return """{
    "page": int, // 1-indexed page number, contiguous starting at 1
    "page_description": str // A 2-4 sentence prose description of this page. Covers where the scene takes place, which characters are present, and the single visual moment or event that happens. Written as natural prose, not labels or bullet points.
}"""


@dataclass
class PageOutlineOutput(JsonSerializable):
    """Output from outline.generate_page_outline() - a page-by-page plan."""

    pages: List[PageOutlineNode]

    @staticmethod
    def schema() -> str:
        return f"""{{
    "pages": [
        {PageOutlineNode.schema()}
    ]
}}"""


# =============================================================================
# SCRIPTER OUTPUTS
# =============================================================================


@dataclass
class ScriptNode(JsonSerializable):
    """A single page/node from scripter.prepare_story()

    The script node decomposes a page outline into:
    - dialog: Optional dict mapping character names to their spoken lines
    - narrator: Optional narrator text
    - shot: Image template describing the visual composition (includes location context)
    """

    page: int
    dialog: Dict[str, str] | None  # Character name -> spoken line, or None if no dialog
    narrator: str | None  # Narrator text, or None if no narration
    shot: str  # Image template: lens, location context, character poses/expressions

    @staticmethod
    def schema() -> str:
        return """{
    "page": int, // 1-indexed page number, must match the outline

    "dialog": { // Optional - character dialog on this page
        "<character_name>": "<what they said>",
        ...
    } | null,

    "narrator": "<narrator text>" | null, // Optional narrator text for this page

    "shot": str // Image template for illustration: lens type (wide/medium/close-up), location context, and for each character present: their pose and expression. Example: "Wide shot. Kitchen interior with flour-dusted counter. Benny (bunny) stands on tiptoe reaching for a cookie jar, eyes wide with excitement. Mom (bunny) watches from doorway, arms crossed, eyebrow raised."
}"""


@dataclass
class ScriptOutput(JsonSerializable):
    """Output from scripter.prepare_story()"""

    pages: List[ScriptNode]

    @staticmethod
    def schema() -> str:
        return f"""{{
    "pages": [
        {ScriptNode.schema()}
    ]
}}"""


# =============================================================================
# ILLUSTRATOR OUTPUTS
# =============================================================================


@dataclass
class SketchOutput(JsonSerializable):
    """Output from illustrator.sketch()"""

    prompt: str
    image: str  # Base64 encoded image


@dataclass
class PropSketch(JsonSerializable):
    """A key prop extracted from the script with its reference image."""

    visual_description: str  # Compact visual description (e.g. "red wooden sled with curved runners")
    image: str  # Base64 encoded reference image

    @staticmethod
    def schema() -> str:
        return """{
    "name": string, // Short prop name (1-3 words)
    "visual_description": string // Compact visual description for recall and image generation (< 15 words, e.g. "red wooden sled with curved metal runners")
}"""


@dataclass
class PageSketchOutput(JsonSerializable):
    """Output from illustrator.sketch_page() - includes matched entities for reference tracking."""

    prompt: str
    image: str  # Base64 encoded image
    matched_character_names: List[str]  # Character names that appear in the shot
    matched_prop_names: List[str]  # Prop names that appear in the shot


# =============================================================================
# ILLUSTRATED SCRIPT OUTPUTS
# =============================================================================


@dataclass
class IllustratedScriptNode(JsonSerializable):
    """A single illustrated script node - wraps ScriptNode with generated image.

    This follows the pattern of ConceptIllustratedOutput which wraps ConceptOutput
    with illustration data. The page number is accessible via node.page.

    Contains three image stages:
    1. Original sketch (image_url) - base illustration without style
    2. Styled version (styled_image_url) - with art direction applied
    3. Critic-revised version (critic_revised_image_url) - after QC critique and revision

    Also tracks which characters and props were matched during generation for consistent
    critique and revision reference images.
    """

    node: ScriptNode
    status: Literal["completed", "error"]
    image_url: str | None = None
    image_prompt: str | None = None
    styled_image_url: str | None = None
    styled_image_prompt: str | None = None
    critic_revised_image_url: str | None = None
    critic_revised_image_prompt: str | None = None
    lettered_image_url: str | None = None  # Image with speech bubbles/narrator captions
    lettered_image_prompt: str | None = None  # Prompt used for lettering
    error: str | None = None
    # Matched entities from generation (for critique reference images)
    matched_character_names: List[str] = field(default_factory=list)
    matched_prop_names: List[str] = field(default_factory=list)


# =============================================================================
# PUBLISHER OUTPUTS
# =============================================================================


# Device layout constants for aspect ratio generation
DEVICE_LAYOUTS = {
    "ipad": {"width": 2048, "height": 1536, "ratio": 4 / 3, "str_ratio": "4:3"},
    "iphone": {"width": 1376, "height": 768, "ratio": 16 / 9, "str_ratio": "16:9"},
}


@dataclass
class PublishedPageOutput(JsonSerializable):
    """A published page with device-specific aspect ratio images.

    The iPad image comes directly from the illustration pipeline (already 4:3).
    The iPhone (16:9) version is generated via Gemini outpainting.
    """

    illustrated_node: IllustratedScriptNode  # Source illustration
    status: Literal["completed", "error"]
    ipad_image: str | None = None  # 4:3 ratio image (2048x1536)
    iphone_image: str | None = None  # 16:9 ratio image (1376x768)
    error: str | None = None
