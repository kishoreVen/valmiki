"""
TemplateRegistry - Loads Jinja2 templates and produces StructuredPrompt objects.

Replaces the old PromptRegistry (which loaded from Python modules / Firebase).
Templates live in the templates/ directory as .j2 files with YAML frontmatter.

Usage:
    from story_engine.production.template_registry import templates

    # System prompt (no variables needed)
    structured = templates.render("concept/create.system")
    query = Query(structured_prompt=structured, query_text=user_prompt)

    # User prompt with variables
    user_text = templates.render_text("concept/create.user",
        theme="dragons", characters=char_list, age_range="4-5"
    )
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import jinja2

from story_engine.lib.model_router.query import StructuredPrompt

logger = logging.getLogger(__name__)

# Default templates directory (relative to repo root)
_DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parent / "prompts"


def _parse_frontmatter(source: str) -> tuple[dict, str]:
    """Split YAML frontmatter from template body.

    Returns (metadata_dict, body_string).
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", source, re.DOTALL)
    if not match:
        return {}, source

    frontmatter_text = match.group(1)
    body = match.group(2)

    # Simple key: value parsing (no full YAML dependency needed)
    metadata = {}
    for line in frontmatter_text.strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()

    return metadata, body


def _extract_block(rendered: str, block_name: str) -> Optional[str]:
    """Extract content from a rendered Jinja block marker.

    We render blocks individually by using the block isolation approach.
    """
    return rendered.strip() if rendered.strip() else None


class TemplateRegistry:
    """Loads .j2 templates and produces StructuredPrompt objects or plain text."""

    _instance: Optional["TemplateRegistry"] = None

    @classmethod
    def get_instance(cls, templates_dir: Optional[Path] = None) -> "TemplateRegistry":
        if cls._instance is None:
            cls._instance = TemplateRegistry(templates_dir or _DEFAULT_TEMPLATES_DIR)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def __init__(self, templates_dir: Path) -> None:
        self.templates_dir = Path(templates_dir)
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.templates_dir)),
            undefined=jinja2.StrictUndefined,
            keep_trailing_newline=True,
        )
        self._source_cache: Dict[str, str] = {}
        logger.info(f"TemplateRegistry initialized with templates from {self.templates_dir}")

    def _resolve_name(self, name: str) -> str:
        """Resolve template name to file path.

        Accepts both 'concept/create.system' and 'concept/create.system.j2'.
        """
        if not name.endswith(".j2"):
            name = name + ".j2"
        return name

    def _get_source(self, template_name: str) -> str:
        """Get raw template source (cached)."""
        if template_name not in self._source_cache:
            path = self.templates_dir / template_name
            self._source_cache[template_name] = path.read_text()
        return self._source_cache[template_name]

    def _render_block(self, template_name: str, block_name: str, context: Dict[str, Any]) -> Optional[str]:
        """Render a single block from a template."""
        source = self._get_source(template_name)
        _, body = _parse_frontmatter(source)

        # Create a child template that only renders the specified block
        block_template_source = f"{{% extends '__base' %}}"
        # We need a different approach - render the full template and extract blocks

        # Instead, we'll render block-specific templates
        try:
            # Create a temporary environment with the body as a base
            env = jinja2.Environment(
                loader=jinja2.DictLoader({
                    "__base": body,
                    "__render_block": f"{{% extends '__base' %}}"
                }),
                undefined=jinja2.StrictUndefined,
            )
            base_template = env.get_template("__base")

            # Check if block exists
            if block_name not in base_template.blocks:
                return None

            # Render just the block
            rendered = base_template.render(**context)
        except jinja2.TemplateError:
            return None

        return None  # Fallback

    def render(self, name: str, **context: Any) -> StructuredPrompt:
        """Render a template into a StructuredPrompt.

        Extracts base_instruction, sections, critical_requirements, and
        requirements from the template's Jinja blocks.

        Args:
            name: Template name (e.g., 'concept/create.system')
            **context: Variables to pass to the template

        Returns:
            StructuredPrompt with populated fields
        """
        template_name = self._resolve_name(name)
        source = self._get_source(template_name)
        metadata, body = _parse_frontmatter(source)

        # Parse the template to extract blocks
        env = jinja2.Environment(
            loader=jinja2.DictLoader({"_template": body}),
            undefined=jinja2.StrictUndefined,
        )
        template = env.get_template("_template")

        # Render each block separately by creating block-extracting templates
        blocks = {}
        for block_name in ["base_instruction", "sections", "critical_requirements", "requirements"]:
            if block_name in template.blocks:
                extractor_source = f"""{{% extends "_template" %}}{{% block {block_name} %}}{{{{ super() }}}}{{% endblock %}}"""
                # Actually, simpler: render the whole template, then parse blocks from markers

        # Simpler approach: use marker-based extraction
        # Wrap each block with markers, then render and split
        marked_body = body
        for block_name in ["base_instruction", "sections", "critical_requirements", "requirements"]:
            marked_body = marked_body.replace(
                f"{{% block {block_name} %}}",
                f"<<<BLOCK:{block_name}>>>{{% block {block_name} %}}"
            )
            marked_body = marked_body.replace(
                f"{{% endblock %}}",
                f"{{% endblock %}}<<<ENDBLOCK>>>",
                1  # Only replace first occurrence for this block
            )

        # Re-approach: since endblock doesn't specify which block, use sequential parsing
        # Let's use a clean regex-based block extraction from the raw source instead
        blocks = self._extract_blocks_from_source(body, context)

        base_instruction = blocks.get("base_instruction", "")
        sections = self._parse_sections(blocks.get("sections", ""))
        critical_requirements = self._parse_requirements(blocks.get("critical_requirements", ""))
        requirements = self._parse_requirements(blocks.get("requirements", ""))

        return StructuredPrompt(
            base_instruction=base_instruction,
            sections=sections,
            critical_requirements=critical_requirements,
            requirements=requirements,
        )

    def _extract_blocks_from_source(self, body: str, context: Dict[str, Any]) -> Dict[str, str]:
        """Extract and render each block from template source."""
        result = {}
        block_names = ["base_instruction", "sections", "critical_requirements", "requirements"]

        for block_name in block_names:
            # Find block content in raw source
            pattern = rf"\{{% block {block_name} %}}\s*(.*?)\s*\{{% endblock %}}"
            match = re.search(pattern, body, re.DOTALL)
            if match:
                block_content = match.group(1)
                # Render the block content as a standalone template
                try:
                    block_template = jinja2.Environment(
                        undefined=jinja2.StrictUndefined
                    ).from_string(block_content)
                    result[block_name] = block_template.render(**context).strip()
                except jinja2.UndefinedError as e:
                    logger.warning(f"Missing variable in {block_name}: {e}")
                    result[block_name] = block_content.strip()

        return result

    def _parse_sections(self, sections_text: str) -> Dict[str, str]:
        """Parse rendered sections text into a dict.

        Sections are separated by ## headers in the template.
        """
        if not sections_text:
            return {}

        sections = {}
        current_name = None
        current_lines: List[str] = []

        for line in sections_text.splitlines():
            if line.startswith("## "):
                if current_name is not None:
                    sections[current_name] = "\n".join(current_lines).strip()
                current_name = line[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_name is not None:
            sections[current_name] = "\n".join(current_lines).strip()

        return sections

    def _parse_requirements(self, requirements_text: str) -> List[str]:
        """Parse rendered requirements text into a list.

        Requirements are lines starting with '- '.
        Multi-line requirements are joined until the next '- ' line.
        """
        if not requirements_text:
            return []

        requirements = []
        current: List[str] = []

        for line in requirements_text.splitlines():
            if line.startswith("- "):
                if current:
                    requirements.append("\n".join(current))
                current = [line[2:]]  # Strip the '- ' prefix
            elif current:
                current.append(line)

        if current:
            requirements.append("\n".join(current))

        return requirements

    def render_text(self, name: str, **context: Any) -> str:
        """Render a template into plain text (for user prompts).

        For user-type templates that only have base_instruction,
        this returns the rendered base_instruction directly.

        Args:
            name: Template name
            **context: Variables to pass

        Returns:
            Rendered text string
        """
        prompt = self.render(name, **context)
        return prompt.base_instruction

    def get_template_source(self, name: str) -> str:
        """Get raw template source for the web editor.

        Args:
            name: Template name

        Returns:
            Raw .j2 file contents
        """
        template_name = self._resolve_name(name)
        return self._get_source(template_name)

    def save_template(self, name: str, source: str) -> None:
        """Save edited template source (from web editor).

        Args:
            name: Template name
            source: New template source
        """
        template_name = self._resolve_name(name)
        path = self.templates_dir / template_name
        path.write_text(source)
        # Invalidate cache
        self._source_cache.pop(template_name, None)
        logger.info(f"Template saved: {template_name}")

    def list_templates(self) -> List[Dict[str, str]]:
        """List all available templates with metadata.

        Returns:
            List of dicts with 'name', 'type', 'description' keys
        """
        result = []
        for path in sorted(self.templates_dir.rglob("*.j2")):
            if path.name.startswith("_"):
                continue
            rel = path.relative_to(self.templates_dir)
            name = str(rel).removesuffix(".j2")
            source = path.read_text()
            metadata, _ = _parse_frontmatter(source)
            result.append({
                "name": name,
                "type": metadata.get("type", "unknown"),
                "description": metadata.get("description", ""),
                "path": str(rel),
            })
        return result

    def get_template_variables(self, name: str) -> List[str]:
        """Extract variable names from a template (for the web UI preview).

        Returns:
            List of variable names found in {{ ... }} expressions
        """
        template_name = self._resolve_name(name)
        source = self._get_source(template_name)
        _, body = _parse_frontmatter(source)
        # Find all {{ variable }} patterns, excluding block/endblock
        variables = set()
        for match in re.finditer(r"\{\{\s*(\w+)", body):
            var = match.group(1)
            if var not in ("super", "self"):
                variables.add(var)
        return sorted(variables)

    def reload(self) -> None:
        """Clear caches and reload templates from disk."""
        self._source_cache.clear()
        logger.info("Template caches cleared")


# Module-level convenience functions
def _get_registry() -> TemplateRegistry:
    return TemplateRegistry.get_instance()


templates = type("TemplateAccessor", (), {
    "render": staticmethod(lambda name, **ctx: _get_registry().render(name, **ctx)),
    "render_text": staticmethod(lambda name, **ctx: _get_registry().render_text(name, **ctx)),
    "get_template_source": staticmethod(lambda name: _get_registry().get_template_source(name)),
    "save_template": staticmethod(lambda name, source: _get_registry().save_template(name, source)),
    "list_templates": staticmethod(lambda: _get_registry().list_templates()),
    "get_template_variables": staticmethod(lambda name: _get_registry().get_template_variables(name)),
    "reload": staticmethod(lambda: _get_registry().reload()),
})()


# Backwards compatibility: get_prompt() shim
def get_prompt(key: str) -> StructuredPrompt:
    """Backwards-compatible prompt getter.

    Translates old dot-notation keys to template paths:
        'director.create_concept' → 'concept/create.system'
        'director.create_concept_user' → 'concept/create.user'
        'review.concept' → 'concept/review.system'
        'review.concept_context' → 'concept/review.context'
        'outline.create' → 'outline/create.system'
        'script.review' → 'script/review.system'
        'illustrator.compact_prompt' → 'illustrator/compact_prompt.system'
        'character_designer.expand' → 'character/expand.system'
        'video_editor.enhance_scene' → 'video_editor/enhance_scene.system'
    """
    # Key translation map
    _KEY_MAP = {
        # Concept (director)
        "director.create_concept": "concept/create.system",
        "director.create_concept_user": "concept/create.user",
        "director.revise_concept": "concept/revise.system",
        "director.revise_concept_user": "concept/revise.user",
        "review.concept": "concept/review.system",
        "review.concept_context": "concept/review.context",
        # Outline
        "outline.create": "outline/create.system",
        "outline.create_user": "outline/create.user",
        "outline.revise": "outline/revise.system",
        "outline.revise_user": "outline/revise.user",
        "outline.review": "outline/review.system",
        "outline.review_context": "outline/review.context",
        # Script
        "script.create": "script/create.system",
        "script.create_user": "script/create.user",
        "script.revise": "script/revise.system",
        "script.revise_user": "script/revise.user",
        "script.review": "script/review.system",
        "script.review_context": "script/review.context",
        # Illustrator
        "illustrator.compact_prompt": "illustrator/compact_prompt.system",
        "illustrator.substitute_shot": "illustrator/substitute_shot.system",
        "illustrator.critique": "illustrator/critique.system",
        "illustrator.critique_context": "illustrator/critique.context",
        "illustrator.revise": "illustrator/revise.system",
        "illustrator.revise_image": "illustrator/revise_image.user",
        "illustrator.regenerate_image": "illustrator/regenerate_image.user",
        "illustrator.style_transfer": "illustrator/style_transfer.user",
        "illustrator.extract_props": "illustrator/extract_props.system",
        "illustrator.triage": "illustrator/triage.system",
        # Character
        "character_designer.expand": "character/expand.system",
        "character_designer.compact_sketch": "character/compact_sketch.system",
        "character_designer.compact_visual": "character/compact_visual.system",
        # Prose
        "prose.create": "prose/create.system",
        "prose.create_user": "prose/create.user",
        "prose.revise": "prose/revise.system",
        "prose.revise_user": "prose/revise.user",
        "prose.review": "prose/review.system",
        "prose.review_context": "prose/review.context",
        # Video Editor
        "video_editor.enhance_scene": "video_editor/enhance_scene.system",
        "video_editor.enhance_shots": "video_editor/enhance_shots.system",
        "video_editor.review_scene": "video_editor/review_scene.system",
        "video_editor.review_scene_context": "video_editor/review_scene.context",
        "video_editor.revise_scene": "video_editor/revise_scene.system",
        "video_editor.review_shots": "video_editor/review_shots.system",
        "video_editor.review_shots_context": "video_editor/review_shots.context",
        "video_editor.revise_shots": "video_editor/revise_shots.system",
        "video_editor.generate_opening_frame_prompt": "video_editor/generate_opening_frame.system",
    }

    template_name = _KEY_MAP.get(key)
    if template_name is None:
        raise KeyError(f"Unknown prompt key: {key}. Available: {sorted(_KEY_MAP.keys())}")

    return _get_registry().render(template_name)
