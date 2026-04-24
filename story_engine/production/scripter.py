
"""Script generation — converts a page outline into a read-aloud picture book script.

Takes the finalized PageOutlineOutput and characters, then decomposes each page
into dialog, narrator text, and an image shot template for illustration.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from story_engine.lib.model_router.model_interface import Capability
from story_engine.lib.model_router.query import Query, StructuredPrompt
from story_engine.lib.model_router.router import ModelRouter
from story_engine.lib.quality_control.playbooks.global_solve import GlobalSolveConfig
from story_engine.lib.quality_control.pipeline import QualityControlPipeline
from story_engine.lib.quality_control.types import (
    CritiqueRequest,
    QualityControlConfig,
    QCChecklistItem,
    QCFeedbackWithChecklist,
    QCResult,
    QCState,
)
from story_engine.elements import character
from story_engine.lib import output_formatting
from story_engine.production.data_operators import (
    ConceptOutput,
    PageOutlineOutput,
    ScriptNode,
    ScriptOutput,
)
from story_engine.production.template_registry import templates
from story_engine.production.style_references import (
    SHOT_SPECS,
    get_style_from_string,
)

logger = logging.getLogger(__name__)


@dataclass
class ScripterConfig:
    """Configuration for the Scripter component."""

    model_interface: str = "openai_gpt52"
    on_failure_model_interface: str = "anthropic_opus45"
    critic_interfaces: List[str] = field(
        default_factory=lambda: ["openai_gpt52", "gemini_flash3"]
    )


class Scripter:
    """Converts a page outline into a read-aloud picture book script."""

    def __init__(
        self, config: ScripterConfig, router: ModelRouter | None = None
    ) -> None:
        self.config = config
        self.router = router or ModelRouter()

    def _fix_page_numbers(self, nodes: List[ScriptNode]) -> List[ScriptNode]:
        """Ensure page numbers are sequential starting from 1.

        The LLM may not reliably produce correct page values, so this
        post-processing step ensures they are sequential.
        """
        fixed_nodes: List[ScriptNode] = []
        for idx, node in enumerate(nodes):
            expected_page = idx + 1
            if node.page != expected_page:
                node = ScriptNode(
                    page=expected_page,
                    dialog=node.dialog,
                    narrator=node.narrator,
                    shot=node.shot,
                )
            fixed_nodes.append(node)
        return fixed_nodes

    def _format_checklist_for_revision(self, checklist: List[QCChecklistItem]) -> str:
        """Format incomplete checklist items for the revision prompt.

        Shows only incomplete items, sorted by priority (P0 first).
        """
        if not checklist:
            return "No specific checklist items."

        incomplete = [item for item in checklist if not item.completed]
        if not incomplete:
            return "All previous checklist items have been addressed."

        priority_order = {"P0": 0, "P1": 1, "P2": 2}
        sorted_items = sorted(
            incomplete,
            key=lambda x: (priority_order.get(x.priority, 3), getattr(x, "focus_area", ""))
        )

        lines = []
        for item in sorted_items:
            focus_ref = f" [{getattr(item, 'focus_area', '').upper()}]" if hasattr(item, "focus_area") and getattr(item, "focus_area", "") else ""
            lines.append(
                f"[{item.priority}]{focus_ref} {item.description}\n"
                f"    Done when: {item.done_when}"
            )
        return "\n\n".join(lines)

    def _get_model_response(
        self,
        structured_prompt: StructuredPrompt,
        prompt_data: str,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        thinking: bool = False
    ) -> Dict[str, Any]:
        """Get response from model with fallback on empty response."""
        query = Query(
            structured_prompt=structured_prompt,
            query_text=prompt_data,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repetitions=2,
        )

        response = self.router.get_response(
            query, Capability.TEXT_THINKING if thinking else Capability.TEXT, self.config.model_interface
        )

        if response["text"] == "":
            response = self.router.get_response(
                query, Capability.TEXT, self.config.on_failure_model_interface
            )
            logger.info("Using fallback model for response")

        return response

    def _build_character_str(self, characters: List[character.Character]) -> List[str]:
        """Build prompt-ready character descriptions."""
        return [
            char.prompt_data.capability_prompt[Capability.TEXT] for char in characters
        ]

    def prepare_story(
        self,
        page_outline: PageOutlineOutput,
        characters: List[character.Character],
        director_vision: ConceptOutput,
    ) -> List[ScriptNode]:
        """Generate a script from the page outline and characters.

        Args:
            page_outline: The page-by-page outline to convert.
            characters: List of characters for the story.
            director_vision: The director's vision (includes illustration_style).

        Returns:
            List of script nodes for the entire story.
        """
        character_str = self._build_character_str(characters)

        style_enum = get_style_from_string(director_vision.illustration_style)
        shot_style_spec = SHOT_SPECS.get(style_enum, "")

        prompt_data = templates.render_text("script/create.user",
            characters=character_str,
            page_outline=page_outline.to_json(indent=2),
            illustration_style=director_vision.illustration_style,
            shot_style_spec=shot_style_spec,
        )

        response = self._get_model_response(
            templates.render("script/create.system"),
            prompt_data,
            temperature=random.uniform(0.6, 0.8),
            top_p=random.uniform(0.75, 0.95),
            thinking=True,
        )

        logger.info(f"Full script generated --> RAW:\n\n{response['text']}")

        script_output = output_formatting.safe_dataclass_decode(ScriptOutput, response["text"])
        nodes = self._fix_page_numbers(script_output.pages)

        logger.info(f"Generated {len(nodes)} pages from outline")
        return nodes

    def apply_critic(
        self,
        page_outline: PageOutlineOutput,
        characters: List[character.Character],
        director_vision: ConceptOutput,
        previous_script: List[ScriptNode],
        critic_feedback: QCFeedbackWithChecklist,
    ) -> List[ScriptNode]:
        """Revise script based on critic feedback.

        Args:
            page_outline: The page outline (source of truth).
            characters: List of characters for the story.
            director_vision: The director's vision (includes illustration_style).
            previous_script: The script to revise.
            critic_feedback: Feedback from the critic.

        Returns:
            List of revised script nodes.
        """
        character_str = self._build_character_str(characters)
        checklist_str = self._format_checklist_for_revision(critic_feedback.checklist)

        style_enum = get_style_from_string(director_vision.illustration_style)
        shot_style_spec = SHOT_SPECS.get(style_enum, "")

        current_script_output = ScriptOutput(pages=previous_script)

        prompt_data = templates.render_text("script/revise.user",
            page_outline=page_outline.to_json(indent=2),
            characters=character_str,
            current_script=current_script_output.to_json(indent=2),
            critic_feedback=critic_feedback.feedback.feedback,
            checklist_items=checklist_str,
        )

        response = self._get_model_response(
            templates.render("script/revise.system"),
            prompt_data,
            thinking=True,
        )

        logger.info(f"Full script revision generated --> RAW:\n\n{response['text']}")

        script_output = output_formatting.safe_dataclass_decode(ScriptOutput, response["text"])
        nodes = self._fix_page_numbers(script_output.pages)

        logger.info(f"Revised script: {len(previous_script)} pages -> {len(nodes)} pages")
        return nodes

    def _create_feedback_decoder(self) -> Callable[[str, str], QCFeedbackWithChecklist]:
        """Create a feedback decoder function for QC pipeline."""
        def decoder(text: str, model: str) -> QCFeedbackWithChecklist:
            data = output_formatting.safe_json_decode(text)
            return QCFeedbackWithChecklist.from_flat_dict(data, model=model)
        return decoder

    def run_script_qc(
        self,
        script: List[ScriptNode],
        page_outline: PageOutlineOutput,
        characters: List[character.Character],
        director_vision: ConceptOutput,
        control_guide: StructuredPrompt,
        build_context: Callable[[List[QCChecklistItem], int], str],
        max_iterations: int = 5,
        state: QCState | None = None,
        on_feedback: Callable[[QCFeedbackWithChecklist, int], None] | None = None,
        on_revision: Callable[[List[ScriptNode], int], None] | None = None,
    ) -> QCResult:
        """Run quality control loop for script using GlobalSolve.

        Args:
            script: Initial script nodes to evaluate.
            page_outline: The page outline (source of truth for revisions).
            characters: Story characters.
            director_vision: Director's concept (includes illustration_style).
            control_guide: The control guide (system prompt) for the critic LLM.
            build_context: Function to build context for critic (checklist, iteration).
            max_iterations: Maximum QC iterations.
            state: Optional state for restart recovery.
            on_feedback: Callback when feedback is received.
            on_revision: Callback when revision is complete.

        Returns:
            QCResult with final script JSON and approval status.
        """
        playbook_config = GlobalSolveConfig(
            max_iterations=max_iterations,
            model_interfaces=self.config.critic_interfaces,
            feedback_decoder=self._create_feedback_decoder(),
        )
        qc_config = QualityControlConfig(
            playbook="GlobalSolve",
            playbook_config=playbook_config,
        )

        current_script = script
        iteration = state.iteration if state else 0

        def revise_fn(content: str, feedback: QCFeedbackWithChecklist) -> str:
            nonlocal current_script, iteration

            revised_script = self.apply_critic(
                page_outline=page_outline,
                characters=characters,
                director_vision=director_vision,
                previous_script=current_script,
                critic_feedback=feedback,
            )
            current_script = revised_script
            iteration += 1

            if on_revision:
                on_revision(revised_script, iteration)

            return ScriptOutput(pages=revised_script).to_json(indent=2)

        initial_content = ScriptOutput(pages=script).to_json(indent=2)
        initial_context = build_context(
            state.accumulated_checklist if state else [],
            iteration,
        )

        qc = QualityControlPipeline(config=qc_config, router=self.router)
        return qc.run(
            request=CritiqueRequest(
                content=initial_content,
                context=initial_context,
                control_guide=control_guide,
            ),
            revise_fn=revise_fn,
            state=state,
            on_feedback=on_feedback,
        )
