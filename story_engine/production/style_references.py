
# Style reference image loader for illustration pipeline.
# Loads style reference images from Firebase Storage for use with diffusion models.

from enum import Enum
from typing import Dict
from PIL import Image
import functools
import io

from story_engine.lib.local_storage import download_image_from_storage


class IllustrationStyle(str, Enum):
    """Supported illustration styles for children's books."""

    ABSTRACT = "abstract"
    CARTOON = "cartoon"
    LINE_DRAWING = "line_drawing"
    MANGA = "manga"
    MOODY = "moody"
    REALISTIC = "realistic"
    VINTAGE = "vintage"
    WHIMSICAL = "whimsical"
    WIMMELBUCH = "wimmelbuch"

CARTOON_STYLE_SPEC="""
Medium: Imitate a mixed-media traditional technique, specifically gouache paint layered with dry colored pencil. Ensure textures are visible, with a grainy, paper-like finish rather than digital smoothness.
Line Work: Use soft, undefined edges instead of harsh black outlines. Define shapes through color blocking and texture contrast.
"""

LINE_DRAWING_STYLE_SPEC="""
Hand-drawn ink illustration, doodle aesthetic, loose shaky linework, distinct cross-hatching texture, patterns (stripes, bricks), uneven ink bleed, sketch.
Palette Constraint: Limit output to 3 tones: Black (Line), White (Negative Space), Cyan (Fill).
Line Weight: Medium-Thin, variable width (simulating a fountain pen or felt tip).
Texture Overlay: Paper grain / slight noise (to prevent "digital clean" look).
"""

MOODY_DRAWING_STYLE_SPEC="""
Medium: Pen & Ink with Watercolor Wash.
Line Work: Loose, scratchy, expressive black ink contours.
Texture: Visible watercolor bleeding, paper grain, and imperfect "hand-drawn" edges.
"""

VINTAGE_DRAWING_STYLE_SPEC="""
Artistic Medium: Mid-century gouache and ink wash painting on heavy cardstock.
Era/Influence: 1950s-1960s classic children's fairy tale book illustration.
Texture & Finish: Visible coarse paper grain, matte texture, slight vintage yellowing or aging on the page edges, soft vignette.
Line Work: Soft, painterly edges rather than sharp vector outlines. No heavy black inking.
"""

WIMMELBUCH_DRAWING_STYLE_SPEC="""
Line Work: Ligne claire (Clear Line) style; distinct, consistent, thin black ink outlines for all characters and objects.
Rendering: Flat, matte fill (cel-shaded) with no gradients.
"""

ABSTRACT_DRAWING_STYLE_SPEC="""
Medium: Digital gouache, dry chalk pastel, textured paper collage
Technique: Lineless art (no outlines), flat color blocking, dry brushstrokes, rough edges, hand-painted aesthetic
Texture: Heavy grain, noise overlay, watercolor paper texture, speckled shading, matte finish
"""

MANGA_DRAWING_STYLE_SPEC="""
Medium: Digital anime-style illustration; soft vector aesthetics with hand-drawn charm.
Line Work: Clean, confident black ink contours with variable line weight (thick outer silhouettes, fine inner details); minimal cross-hatching.
Rendering Technique: Cel-shaded base coloring with soft, airbrushed gradients; hard-edge shadows for depth.
"""

REALISTIC_DRAWING_STYLE_SPEC="""
Art Style: magical realism, soft-focus dreamscape.
Medium: Digital painting mimicking soft pastels and gouache on coarse-grain watercolor paper.
Texture: High-grain paper texture, visible soft chalky strokes, diffused edges, matte finish (no gloss).
"""

WHIMSICAL_DRAWING_STYLE_SPEC="""
Medium: Soft digital painting
Texture: Grainy chalk texture, textured brushstrokes, matte finish
Line Work: No hard outlines (lineless art)
"""


STYLE_SPECS: Dict[IllustrationStyle, str] = {
    IllustrationStyle.ABSTRACT: ABSTRACT_DRAWING_STYLE_SPEC,
    IllustrationStyle.CARTOON: CARTOON_STYLE_SPEC,
    IllustrationStyle.LINE_DRAWING: LINE_DRAWING_STYLE_SPEC,
    IllustrationStyle.MANGA: MANGA_DRAWING_STYLE_SPEC,
    IllustrationStyle.MOODY: MOODY_DRAWING_STYLE_SPEC,
    IllustrationStyle.REALISTIC: REALISTIC_DRAWING_STYLE_SPEC,
    IllustrationStyle.VINTAGE: VINTAGE_DRAWING_STYLE_SPEC,
    IllustrationStyle.WHIMSICAL: WHIMSICAL_DRAWING_STYLE_SPEC,
    IllustrationStyle.WIMMELBUCH: WIMMELBUCH_DRAWING_STYLE_SPEC,
}


# =============================================================================
# SHOT SPECIFICATIONS - Guidelines for scripter shot descriptions per style
# =============================================================================

CARTOON_SHOT_SPEC = """
FRAMING PALETTE (use these exact terms):
- close-up: face fills frame — for emotional peaks
- medium close-up: head and shoulders — for reactions and dialog
- medium shot: waist-up — for expressions and body language
- medium wide shot: full body + environment — for action
- wide shot: environment dominates — for scene establishment
- low-angle shot: camera looks up — for heroic or funny moments
- high-angle shot: camera looks down — for overview or vulnerability

DISTRIBUTION RULES:
- Page 1 MUST be a wide shot or medium wide shot
- At least 2 pages must use wide shot for scene establishment
- At least 2 pages must use close-up or medium close-up
- No more than 2 consecutive pages with the same framing
- At least 1 page must use low-angle or high-angle shot

STYLE NOTES:
- Wide shot of environment with no characters works well for scene establishment
- Max 2 characters per shot
"""

LINE_DRAWING_SHOT_SPEC = """
FRAMING PALETTE (use these exact terms):
- close-up: face fills frame — for emotional beats
- medium shot: waist-up — characters read as simple shapes
- medium wide shot: full body + environment — for context
- wide shot: environment dominates — for setting establishment
- high-angle shot: camera looks down — for overview of scene

DISTRIBUTION RULES:
- Page 1 MUST be a wide shot
- At least 2 pages must use close-up or medium close-up
- At least 2 pages must use wide shot or medium wide shot
- No more than 2 consecutive pages with the same framing
- Max 2 characters per shot (silhouettes must remain readable)

STYLE NOTES:
- Wide shot of environment with no characters works well for setting reveals
- Prioritize clear silhouettes over complex compositions
- Avoid overlapping characters
"""

MOODY_SHOT_SPEC = """
FRAMING PALETTE (use these exact terms):
- close-up: face fills frame — for emotional moments
- medium close-up: head and shoulders — for contemplative moments
- medium shot: waist-up — for quiet character scenes
- wide shot: environment dominates — for atmosphere and isolation
- high-angle shot: camera looks down — for vulnerability and smallness

DISTRIBUTION RULES:
- Page 1 MUST be a wide shot (atmospheric establishment)
- At least 2-3 pages must be wide shots of environment with no characters
- At least 2 pages must use close-up or medium close-up for emotional peaks
- No more than 2 consecutive pages with the same framing
- At least 1 page must use high-angle shot

STYLE NOTES:
- Wide shots of environment with no characters set the atmospheric tone
- Avoid action shots and crowded compositions
"""

VINTAGE_SHOT_SPEC = """
FRAMING PALETTE (use these exact terms):
- close-up: face fills frame — for emotional turns
- medium close-up: head and shoulders — for character focus
- medium shot: waist-up — for composed character scenes
- medium wide shot: full body + environment — for narrative moments
- wide shot: environment dominates — for establishing scenes
- worm's-eye view: ground level looking up — for grand storybook scale

DISTRIBUTION RULES:
- Page 1 MUST be a wide shot (storybook-style establishment)
- At least 2 pages must use wide shot or medium wide shot
- At least 2 pages must use close-up or medium close-up
- No more than 2 consecutive pages with the same framing
- At least 1 page must use worm's-eye view or high-angle shot

STYLE NOTES:
- Wide shot of environment with no characters works well for setting reveals
- Composed, centered framing suits the classic storybook aesthetic
- Avoid complex multi-character arrangements
"""

WIMMELBUCH_SHOT_SPEC = """
FRAMING PALETTE (use these exact terms):
- wide shot: environment with many characters and activities — primary framing
- extreme wide shot: vast scene with tiny figures — for scale
- bird's-eye view: directly overhead — for maps and busy scene overviews
- overhead/isometric view: angled top-down — for detailed activity scenes

DISTRIBUTION RULES:
- ALL pages MUST use wide shot, extreme wide shot, bird's-eye view, or overhead/isometric view
- No close-ups or isolated character shots
- Always describe 3-5 background details or secondary activities per scene

STYLE NOTES:
- Main characters should be findable but part of the busy scene, not isolated
- Wide shots of environment with no named characters are acceptable for setting pages
"""

ABSTRACT_SHOT_SPEC = """
FRAMING PALETTE (use these exact terms):
- close-up: shape/character fills frame — for emotional beats and strong graphic compositions
- medium shot: waist-up — for character-focused scenes
- medium wide shot: full body + environment — for scene context
- wide shot: environment dominates — for setting compositions
- high-angle shot: camera looks down — for graphic pattern effects and overview
- low-angle shot: camera looks up — for dramatic silhouettes

DISTRIBUTION RULES:
- Page 1 MUST be a wide shot
- At least 2 pages must use close-up or medium close-up
- At least 2 pages must use wide shot or medium wide shot
- No more than 2 consecutive pages with the same framing
- At least 1 page must use high-angle or low-angle shot

STYLE NOTES:
- Wide shot of environment with no characters works well for establishing scenes
- Avoid complex perspective — clean, readable compositions suit the lineless style
- Max 2 characters per shot
"""

MANGA_SHOT_SPEC = """
FRAMING PALETTE (use these exact terms):
- extreme close-up: single detail fills frame — eye, hand, object — for high-impact moments
- close-up: face fills frame — for emotional beats
- medium close-up: head and shoulders — for reactions
- medium shot: waist-up — for dialog
- medium wide shot: full body + environment — for action
- wide shot: environment dominates — for scene establishment
- low-angle shot: camera looks up — for power and heroism
- high-angle shot: camera looks down — for vulnerability or overview
- over-the-shoulder shot: behind one character looking at another — for confrontation

DISTRIBUTION RULES:
- Page 1 MUST be a wide shot or extreme wide shot
- At least 2 pages must use close-up or extreme close-up
- At least 2 pages must use wide shot or medium wide shot
- No more than 2 consecutive pages with the same framing
- At least 1 page must use low-angle or high-angle shot

STYLE NOTES:
- Wide shot of environment with no characters works well for scene and goal reveals
- Varied framing is the defining feature of this style — monotony is a failure
- Avoid dutch angles (unreliable in illustration styles)
"""

REALISTIC_SHOT_SPEC = """
FRAMING PALETTE (use these exact terms):
- extreme close-up: single detail fills frame — for intimate emotional peaks
- close-up: face fills frame — for emotional moments
- medium close-up: head and shoulders — for character focus
- medium shot: waist-up — for character-environment interaction
- medium wide shot: full body + environment — for grounded scenes
- wide shot: environment dominates — for scene establishment
- extreme wide shot: tiny figures in landscape — for journey and scale
- low-angle shot: camera looks up — for heroic or aspirational moments
- worm's-eye view: ground level looking up — for towering scale

DISTRIBUTION RULES:
- Page 1 MUST be a wide shot or extreme wide shot
- At least 2-3 pages must use wide shot or extreme wide shot (environment-dominant, no characters required)
- At least 2 pages must use close-up or extreme close-up for emotional peaks
- No more than 2 consecutive pages with the same framing
- At least 1 page must use low-angle or worm's-eye view

STYLE NOTES:
- Characters must feel grounded in their environment — use wide and medium wide shots frequently
- Lens variety is especially effective in this style
"""

WHIMSICAL_SHOT_SPEC = """
FRAMING PALETTE (use these exact terms):
- close-up: face fills frame — for wonder/awe moments
- medium close-up: head and shoulders — for gentle reactions
- medium shot: waist-up — default for character interaction
- medium wide shot: full body + environment — for action beats
- wide shot: environment dominates — for scene establishment (characters optional)
- low-angle shot: camera at ground level looking up — to make things feel magical/towering

DISTRIBUTION RULES:
- Page 1 MUST be a wide shot
- At least 2 pages must use close-up or medium close-up
- At least 2 pages must use wide shot or medium wide shot
- No more than 2 consecutive pages with the same framing
- At least 1 page must use low-angle or high-angle shot

STYLE NOTES:
- Wide shot of environment with no characters works well for setting and goal reveals
- Prefer centered, gentle compositions
- Avoid dutch angles and extreme perspective distortion
"""

SHOT_SPECS: Dict[IllustrationStyle, str] = {
    IllustrationStyle.ABSTRACT: ABSTRACT_SHOT_SPEC,
    IllustrationStyle.CARTOON: CARTOON_SHOT_SPEC,
    IllustrationStyle.LINE_DRAWING: LINE_DRAWING_SHOT_SPEC,
    IllustrationStyle.MANGA: MANGA_SHOT_SPEC,
    IllustrationStyle.MOODY: MOODY_SHOT_SPEC,
    IllustrationStyle.REALISTIC: REALISTIC_SHOT_SPEC,
    IllustrationStyle.VINTAGE: VINTAGE_SHOT_SPEC,
    IllustrationStyle.WHIMSICAL: WHIMSICAL_SHOT_SPEC,
    IllustrationStyle.WIMMELBUCH: WIMMELBUCH_SHOT_SPEC,
}


STYLE_PATHS: Dict[IllustrationStyle, str] = {
    IllustrationStyle.ABSTRACT: "style_references/abstract.png",
    IllustrationStyle.CARTOON: "style_references/cartoon.png",
    IllustrationStyle.LINE_DRAWING: "style_references/line_drawing.png",
    IllustrationStyle.MANGA: "style_references/manga.png",
    IllustrationStyle.MOODY: "style_references/moody.png",
    IllustrationStyle.REALISTIC: "style_references/realistic.png",
    IllustrationStyle.VINTAGE: "style_references/vintage.png",
    IllustrationStyle.WHIMSICAL: "style_references/whimsical.png",
    IllustrationStyle.WIMMELBUCH: "style_references/wimmelbuch.png",
}


@functools.lru_cache(maxsize=16)
def load_style_reference(style: IllustrationStyle) -> Image.Image:
    """Load a style reference image from Firebase Storage.

    Uses LRU cache to avoid repeated downloads during a pipeline run.

    Args:
        style: The illustration style to load

    Returns:
        PIL Image of the style reference

    Raises:
        ValueError: If style is not recognized or image cannot be loaded
    """
    if style not in STYLE_PATHS:
        raise ValueError(f"Unknown illustration style: {style}")

    storage_path = STYLE_PATHS[style]
    image_bytes = download_image_from_storage(storage_path)
    return Image.open(io.BytesIO(image_bytes))


def get_style_from_string(style_str: str) -> IllustrationStyle:
    """Convert a string to IllustrationStyle enum.

    Args:
        style_str: Style name as string (e.g., "watercolor", "whimsical_fantasy")

    Returns:
        Corresponding IllustrationStyle enum value

    Raises:
        ValueError: If style string is not recognized
    """
    try:
        return IllustrationStyle(style_str.lower().replace("-", "_").replace(" ", "_"))
    except ValueError:
        valid_styles = [s.value for s in IllustrationStyle]
        raise ValueError(f"Unknown style '{style_str}'. Valid styles: {valid_styles}")
