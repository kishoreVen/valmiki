
# Pitch a concept for a story, with an art direction, story guidelines, along with a title screen
# based on inputs provided by the user.

import json
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
    QCFeedback,
    QCFeedbackWithChecklist,
    QCResult,
    QCState,
)
from story_engine.elements import character
from story_engine.lib import output_formatting
from story_engine.production.data_operators import (
    ConceptOutput,
    ConceptIllustratedOutput,
)
from story_engine.production.illustrator import Illustrator, IllustratorConfig
from story_engine.production.template_registry import templates
from story_engine.production.prompts.concept import get_concept_structure
from story_engine.production.style_references import IllustrationStyle

import logging

logger = logging.getLogger(__name__)


@dataclass
class DirectorConfig:
    audience_age_range: str = "4"

    title_generation_interface: str = "gemini_pro3_image"

    concept_generation_interface: str = "gemini_flash3"

    critic_interfaces: List[str] = field(
        default_factory=lambda: ["openai_gpt52", "anthropic_opus45"]
    )


class Director:
    def __init__(
        self, config: DirectorConfig, router: ModelRouter | None = None
    ) -> None:
        self.config = config
        self.router = router or ModelRouter()

        # Initialize the illustrator for title shot generation
        self.illustrator = Illustrator(
            IllustratorConfig(
                interface_type=config.title_generation_interface,
                illustration_style="cartoon",  # Temporary default, will be updated per concept
            )
        )

    def generate_concept(
        self,
        theme: str,
        characters: List[character.Character],
        initial_location_hint: str | None = None,
        initial_illustration_style: str | None = None,
    ) -> ConceptOutput:
        """
        Generate a story concept based on the provided theme and characters.

        Args:
            theme: The theme for the story.
            characters: List of characters for the story.
            initial_location_hint: Optional hint about the location setting.
            initial_illustration_style: Optional pre-selected illustration style.
                If provided, the LLM's style selection will be overridden.

        Returns:
            ConceptOutput: The generated story concept (without illustration).
        """
        # Convert characters to their string representation
        character_str = [
            char.prompt_data.capability_prompt[Capability.TEXT] for char in characters
        ]

        # Get concept structure based on character count
        concept_structure = get_concept_structure(len(characters))

        # Create the prompt data
        prompt_data = templates.render_text(
            "concept/create.user",
            theme=theme,
            characters=character_str,
            age_range=self.config.audience_age_range,
            initial_location_hint=initial_location_hint,
            concept_structure=concept_structure,
        )

        # Create a Query object for the model router
        query = Query(
            structured_prompt=templates.render("concept/create.system"),
            query_text=prompt_data,
            temperature=random.uniform(0.7, 0.9),
            top_p=random.uniform(0.8, 1.0),
            repetitions=2,
        )

        # Get response using the model router
        response = self.router.get_response(
            query, Capability.TEXT_THINKING, self.config.concept_generation_interface
        )

        concept = output_formatting.safe_dataclass_decode(
            ConceptOutput, response["text"]
        )

        # Style is chosen randomly (or explicitly), not by the LLM.
        concept.illustration_style = initial_illustration_style or random.choice(
            [s.value for s in IllustrationStyle]
        )

        return concept

    def apply_critic(
        self,
        theme: str,
        characters: List[character.Character],
        previous_concept: ConceptOutput,
        critic_feedback: QCFeedbackWithChecklist,
        initial_location_hint: str | None = None,
        initial_illustration_style: str | None = None,
    ) -> ConceptOutput:
        """
        Re-generate a story concept by incorporating critic feedback.

        Args:
            theme: The theme for the story.
            characters: List of characters for the story.
            previous_concept: The previous ConceptOutput to revise.
            critic_feedback: QCFeedbackWithChecklist from the critic for the concept.
            initial_location_hint: Optional hint about the location setting.
            initial_illustration_style: Optional pre-selected illustration style.
                If provided, the LLM's style selection will be overridden.

        Returns:
            ConceptOutput: The revised story concept (without illustration).
        """
        # Convert characters to their string representation
        character_str = [
            char.prompt_data.capability_prompt[Capability.TEXT] for char in characters
        ]

        # Get concept structure based on character count
        concept_structure = get_concept_structure(len(characters))

        # Create the prompt data with critic feedback
        prompt_data = templates.render_text(
            "concept/revise.user",
            theme=theme,
            characters=character_str,
            age_range=self.config.audience_age_range,
            initial_location_hint=initial_location_hint,
            concept_structure=concept_structure,
            previous_concept=previous_concept.to_json(indent=2),
            critic_feedback=critic_feedback.feedback.feedback,
        )

        query = Query(
            structured_prompt=templates.render("concept/revise.system"),
            query_text=prompt_data,
            repetitions=2,
        )

        response = self.router.get_response(
            query, Capability.TEXT, self.config.concept_generation_interface
        )

        concept = output_formatting.safe_dataclass_decode(
            ConceptOutput, response["text"]
        )

        # Style is chosen randomly (or explicitly), not by the LLM.
        concept.illustration_style = initial_illustration_style or random.choice(
            [s.value for s in IllustrationStyle]
        )

        logger.info("Revised concept generated after applying critic feedback")

        return concept

    def illustrate_concept(
        self,
        concept: ConceptOutput,
        characters: List[character.Character],
    ) -> ConceptIllustratedOutput:
        """
        Generate the title shot image for a finalized concept.

        This method should be called after concept QC is complete to generate
        the title shot image based on the finalized concept.

        Args:
            concept: The finalized concept (after QC) to illustrate.
            characters: List of characters for the story.

        Returns:
            ConceptIllustratedOutput: The concept with title shot image populated.
        """
        # Update illustrator with the illustration style for this concept
        self.illustrator.update_config(illustration_style=concept.illustration_style)

        # Generate styled title shot in a single pass (no separate style transfer step)
        title_shot_prompt = None
        title_shot_image = None
        try:
            styled_sketch = self.illustrator.sketch_styled(
                query=concept.title_shot,
                characters=characters,
            )
            title_shot_prompt = styled_sketch.prompt
            title_shot_image = styled_sketch.image
        except Exception as e:
            logger.warning(f"title_shot_image generation failed: {e}")

        return ConceptIllustratedOutput(
            concept=concept,
            title_shot_prompt=title_shot_prompt,
            title_shot_image=title_shot_image,
        )

    def _create_feedback_decoder(self) -> Callable[[str, str], QCFeedbackWithChecklist]:
        """Create a feedback decoder function for QC pipeline."""
        def decoder(text: str, model: str) -> QCFeedbackWithChecklist:
            data = output_formatting.safe_json_decode(text)
            return QCFeedbackWithChecklist.from_flat_dict(data, model=model)
        return decoder

    def run_concept_qc(
        self,
        concept: ConceptOutput,
        theme: str,
        characters: List[character.Character],
        initial_location_hint: str | None = None,
        initial_illustration_style: str | None = None,
        control_guide=None,  # StructuredPrompt, optional
        build_context: Callable[[list, int], str] | None = None,
        max_iterations: int = 1,
        state: QCState | None = None,
        on_feedback: Callable[[QCFeedbackWithChecklist, int], None] | None = None,
        on_revision: Callable[[ConceptOutput, int], None] | None = None,
    ) -> QCResult:
        """Run quality control loop for concept.

        Args:
            concept: Initial concept to evaluate.
            theme: Story theme.
            characters: Story characters.
            initial_location_hint: Optional hint about the location setting.
            initial_illustration_style: Optional pre-selected illustration style.
            control_guide: The control guide (system prompt) for the critic LLM
                          (defaults to review.concept).
            build_context: Function to build context for critic (no args).
                           Returns context string (characters, etc.) without concept.
            max_iterations: Maximum QC iterations.
            state: Optional state for restart recovery.
            on_feedback: Callback when feedback is received (feedback, iteration).
            on_revision: Callback when revision is complete (new_concept, iteration).

        Returns:
            QCResult with final concept JSON and approval status.
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

        current_concept = concept
        iteration = state.iteration if state else 0

        # Default control guide if not provided
        if control_guide is None:
            control_guide = templates.render("concept/review.system")

        # Default context builder if not provided
        def default_context_builder(checklist: list, iter_num: int) -> str:
            character_str = [
                char.prompt_data.capability_prompt[Capability.TEXT] for char in characters
            ]
            concept_structure = get_concept_structure(len(characters))
            return templates.render_text(
                "concept/review.context",
                age_range=self.config.audience_age_range,
                characters=character_str,
                concept_structure=concept_structure,
                previous_checklist=checklist or "None",
                current_iteration=iter_num,
                max_iterations=max_iterations,
            )

        context_builder = build_context if build_context else default_context_builder
        context = context_builder(
            state.accumulated_checklist if state else [],
            iteration,
        )

        # Exclude illustration_style — it's set by Director (not LLM) and isn't
        # part of ConceptOutput.schema(), so the critic would flag it as a
        # format violation.
        def _concept_for_critic(c: ConceptOutput) -> str:
            d = c.to_dict()
            d.pop("illustration_style", None)
            return json.dumps(d, indent=2)

        def revise_fn(content: str, feedback: QCFeedbackWithChecklist) -> str:
            """Revise concept and return just the new concept JSON."""
            nonlocal current_concept, iteration

            revised_concept = self.apply_critic(
                theme=theme,
                characters=characters,
                previous_concept=current_concept,
                critic_feedback=feedback,
                initial_location_hint=initial_location_hint,
                initial_illustration_style=initial_illustration_style,
            )
            current_concept = revised_concept
            iteration += 1

            if on_revision:
                on_revision(revised_concept, iteration)

            return _concept_for_critic(revised_concept)

        # Build initial request with content and context separated
        initial_content = _concept_for_critic(concept)

        qc = QualityControlPipeline(config=qc_config, router=self.router)
        return qc.run(
            request=CritiqueRequest(
                content=initial_content,
                context=context,
                control_guide=control_guide,
            ),
            revise_fn=revise_fn,
            state=state,
            on_feedback=on_feedback,
        )
