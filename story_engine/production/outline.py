
"""Page outline generation — breaks a dense concept into picture book pages.

Takes the finalized ConceptOutput and produces a page-by-page outline
where each page represents one visual moment a child can follow.
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Callable, List

from story_engine.lib.model_router.model_interface import Query, Capability
from story_engine.lib.model_router.router import ModelRouter
from story_engine.lib.quality_control.playbooks.global_solve import GlobalSolveConfig
from story_engine.lib.quality_control.pipeline import QualityControlPipeline
from story_engine.lib.quality_control.types import (
    CritiqueRequest,
    QualityControlConfig,
    QCFeedbackWithChecklist,
    QCResult,
    QCState,
)
from story_engine.elements import character
from story_engine.lib import output_formatting
from story_engine.production.data_operators import (
    ConceptOutput,
    PageOutlineOutput,
)
from story_engine.production.template_registry import templates

logger = logging.getLogger(__name__)


@dataclass
class OutlineConfig:
    """Configuration for the Outline component."""

    model_interface: str = "openai_gpt52"
    critic_interfaces: List[str] = field(
        default_factory=lambda: ["openai_gpt52", "gemini_flash3"]
    )

    # Page count range
    page_count_min: int = 9
    page_count_max: int = 12


class Outline:
    """Breaks a story concept into a page-by-page picture book outline."""

    def __init__(self, config: OutlineConfig, router: ModelRouter | None = None) -> None:
        self.config = config
        self.router = router or ModelRouter()
        self._page_count: int | None = None

    @property
    def page_count(self) -> int:
        """Target page count. Randomly chosen once per outline generation."""
        if self._page_count is None:
            self._page_count = random.randint(
                self.config.page_count_min, self.config.page_count_max
            )
            logger.info(f"Target page count set to {self._page_count}")
        return self._page_count

    def reset_page_count(self) -> None:
        """Reset so a new page count is chosen on next generation."""
        self._page_count = None

    def generate_page_outline(
        self,
        concept: ConceptOutput,
        characters: List[character.Character],
        illustration_style: str = "",
        shot_style_spec: str = "",
    ) -> PageOutlineOutput:
        """Generate a page-by-page outline from a story concept.

        Args:
            concept: The finalized story concept.
            characters: List of characters for the story.
            illustration_style: Name of the illustration style (e.g., "vintage").
            shot_style_spec: Shot framing guidelines for the style.

        Returns:
            PageOutlineOutput with one entry per page.
        """
        character_str = [
            char.prompt_data.capability_prompt[Capability.TEXT] for char in characters
        ]

        prompt_data = templates.render_text("outline/create.user",
            pitch=concept.pitch,
            characters=character_str,
            page_count=self.page_count,
            illustration_style=illustration_style,
            shot_style_spec=shot_style_spec,
        )

        query = Query(
            structured_prompt=templates.render("outline/create.system"),
            query_text=prompt_data,
            temperature=random.uniform(0.7, 0.9),
            top_p=random.uniform(0.8, 1.0),
            repetitions=2,
        )

        response = self.router.get_response(
            query, Capability.TEXT, self.config.model_interface
        )

        outline = output_formatting.safe_dataclass_decode(
            PageOutlineOutput, response["text"]
        )

        logger.info(f"Page outline generated with {len(outline.pages)} pages")
        return outline

    def apply_critic(
        self,
        concept: ConceptOutput,
        characters: List[character.Character],
        previous_outline: PageOutlineOutput,
        critic_feedback: QCFeedbackWithChecklist,
    ) -> PageOutlineOutput:
        """Revise the page outline based on critic feedback.

        Args:
            concept: The story concept (for context preservation).
            characters: List of characters for the story.
            previous_outline: The outline to revise.
            critic_feedback: Feedback from the critic.

        Returns:
            Revised PageOutlineOutput.
        """
        checklist_str = self._format_checklist_for_revision(critic_feedback.checklist)
        character_str = [
            char.prompt_data.capability_prompt[Capability.TEXT] for char in characters
        ]

        prompt_data = templates.render_text("outline/revise.user",
            pitch=concept.pitch,
            characters=character_str,
            page_count=self.page_count,
            page_outline=previous_outline.to_json(indent=2),
            checklist=checklist_str,
        )

        query = Query(
            structured_prompt=templates.render("outline/revise.system"),
            query_text=prompt_data,
            repetitions=2,
        )

        response = self.router.get_response(
            query, Capability.TEXT, self.config.model_interface
        )

        outline = output_formatting.safe_dataclass_decode(
            PageOutlineOutput, response["text"]
        )

        logger.info(f"Revised outline with {len(outline.pages)} pages")
        return outline

    def _format_checklist_for_revision(self, checklist: List) -> str:
        """Format incomplete checklist items for the revision prompt."""
        if not checklist:
            return "No specific checklist items."

        incomplete = [item for item in checklist if not item.completed]
        if not incomplete:
            return "All previous checklist items have been addressed."

        priority_order = {"P0": 0, "P1": 1, "P2": 2}
        sorted_items = sorted(incomplete, key=lambda x: priority_order.get(x.priority, 3))

        lines = []
        for item in sorted_items:
            lines.append(
                f"[{item.priority}] {item.description}\n"
                f"    Done when: {item.done_when}"
            )
        return "\n\n".join(lines)

    def _create_feedback_decoder(self) -> Callable[[str, str], QCFeedbackWithChecklist]:
        """Create a feedback decoder for the QC pipeline."""
        def decoder(text: str, model: str) -> QCFeedbackWithChecklist:
            data = output_formatting.safe_json_decode(text)
            return QCFeedbackWithChecklist.from_flat_dict(data, model=model)
        return decoder

    def run_outline_qc(
        self,
        outline: PageOutlineOutput,
        concept: ConceptOutput,
        characters: List[character.Character],
        age_range: str = "4",
        illustration_style: str = "",
        shot_style_spec: str = "",
        max_iterations: int = 5,
        state: QCState | None = None,
        on_feedback: Callable[[QCFeedbackWithChecklist, int], None] | None = None,
        on_revision: Callable[[PageOutlineOutput, int], None] | None = None,
    ) -> QCResult:
        """Run quality control loop for the page outline.

        Args:
            outline: Initial outline to evaluate.
            concept: The story concept (for reviewer context).
            characters: Story characters.
            age_range: Target audience age range.
            illustration_style: Name of the illustration style (e.g., "vintage").
            shot_style_spec: Shot framing guidelines for the style.
            max_iterations: Maximum QC iterations.
            state: Optional state for restart recovery.
            on_feedback: Callback when feedback is received.
            on_revision: Callback when revision is complete.

        Returns:
            QCResult with final outline JSON and approval status.
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

        current_outline = outline
        iteration = state.iteration if state else 0

        character_str = [
            char.prompt_data.capability_prompt[Capability.TEXT] for char in characters
        ]

        def build_context(iter_num: int) -> str:
            return templates.render_text("outline/review.context",
                age_range=age_range,
                pitch=concept.pitch,
                characters=character_str,
                illustration_style=illustration_style,
                shot_style_spec=shot_style_spec,
                page_count=self.page_count,
                current_iteration=iter_num,
                max_iterations=max_iterations,
            )

        def revise_fn(content: str, feedback: QCFeedbackWithChecklist) -> str:
            nonlocal current_outline, iteration

            revised = self.apply_critic(
                concept=concept,
                characters=characters,
                previous_outline=current_outline,
                critic_feedback=feedback,
            )
            current_outline = revised
            iteration += 1

            if on_revision:
                on_revision(revised, iteration)

            return revised.to_json(indent=2)

        initial_content = outline.to_json(indent=2)
        initial_context = build_context(iteration)

        control_guide = templates.render("outline/review.system")

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
