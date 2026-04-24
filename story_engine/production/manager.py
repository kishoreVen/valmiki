"""
Manager module for orchestrating the story production pipeline.

This module coordinates the Director, Outline, and Scripter components to produce
a story from input elements (characters, theme).

The Manager supports:
- Step-based execution for incremental progress
- Snapshot serialization for save/load functionality
- Progress callbacks for real-time updates

Pipeline: concept -> concept critic -> illustrate concept -> outline
       -> outline critic -> script -> script critic -> sketch props
       -> illustrations -> illustration critic -> lettering -> publish -> COMPLETED
"""

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

from story_engine.lib.model_router.model_interface import Capability
from story_engine.lib.model_router.router import ModelRouter
from story_engine.production.style_references import (
    SHOT_SPECS,
    get_style_from_string,
)
from story_engine.lib.quality_control.types import (
    QCChecklistItem,
    QCFeedbackWithChecklist,
    QCState,
)
from story_engine.elements import character
from story_engine.production.data_operators import (
    ConceptOutput,
    ConceptIllustratedOutput,
    IllustratedScriptNode,
    PageOutlineOutput,
    PropSketch,
    PublishedPageOutput,
    ScriptNode,
    ScriptOutput,
)
from story_engine.production.cost_tracker import (
    track_step_costs,
    StepCostAccumulator,
)
from story_engine.production.director import Director, DirectorConfig
from story_engine.production.illustrator import Illustrator, IllustratorConfig
from story_engine.production.letterer import Letterer, LettererConfig
from story_engine.production.outline import Outline, OutlineConfig
from story_engine.production.template_registry import templates
from story_engine.production.publisher import Publisher, PublisherConfig
from story_engine.production.scripter import Scripter, ScripterConfig


class PipelineStep(Enum):
    """Enumeration of pipeline steps for tracking progress."""

    NOT_STARTED = "not_started"
    GENERATE_CONCEPT = "generate_concept"
    CRITIC_CONCEPT = "critic_concept"
    ILLUSTRATE_CONCEPT = "illustrate_concept"
    GENERATE_OUTLINE = "generate_outline"
    CRITIC_OUTLINE = "critic_outline"
    GENERATE_SCRIPT = "generate_script"
    CRITIC_SCRIPT = "critic_script"
    SKETCH_PROPS = "sketch_props"
    GENERATE_ILLUSTRATIONS = "generate_illustrations"
    CRITIC_ILLUSTRATIONS = "critic_illustrations"
    GENERATE_LETTERING = "generate_lettering"
    GENERATE_PUBLISH = "generate_publish"
    COMPLETED = "completed"


@dataclass
class StepTiming:
    """Timing data for a single pipeline step."""

    started_at: str  # ISO 8601 timestamp
    completed_at: str | None = None
    duration_ms: int | None = None


@dataclass
class IterationTiming:
    """Timing data for a single critic iteration."""

    iteration: int  # 1-indexed
    started_at: str  # ISO 8601 timestamp
    completed_at: str | None = None
    duration_ms: int | None = None


@dataclass
class PipelineTiming:
    """Timing data for the entire pipeline."""

    pipeline_started_at: str | None = None
    pipeline_completed_at: str | None = None
    pipeline_duration_ms: int | None = None
    steps: Dict[str, StepTiming] = field(default_factory=dict)
    iterations: Dict[str, List[IterationTiming]] = field(default_factory=dict)


@dataclass
class StepCost:
    """Cost data for a single pipeline step (aggregated across all LLM calls)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    call_count: int = 0


@dataclass
class PipelineCosts:
    """Cost data for the entire pipeline."""

    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    steps: Dict[str, StepCost] = field(default_factory=dict)


@dataclass
class ManagerConfig:
    """Configuration for the story production manager."""

    # Maximum critic iterations. 0 = skip critic loop entirely.
    max_concept_critic_iterations: int = 5
    max_outline_critic_iterations: int = 5
    max_script_critic_iterations: int = 3
    max_illustration_critic_iterations: int = 1

    # Component configurations
    director_config: DirectorConfig = field(default_factory=DirectorConfig)
    outline_config: OutlineConfig = field(default_factory=OutlineConfig)
    scripter_config: ScripterConfig = field(default_factory=ScripterConfig)
    illustrator_config: IllustratorConfig = field(
        default_factory=lambda: IllustratorConfig(illustration_style="cartoon")
    )
    letterer_config: LettererConfig = field(
        default_factory=lambda: LettererConfig(illustration_style="cartoon")
    )
    publisher_config: PublisherConfig = field(
        default_factory=lambda: PublisherConfig(illustration_style="cartoon")
    )


@dataclass
class ManagerSnapshot:
    """
    Serializable snapshot of the entire manager state.

    This dataclass captures all inputs and outputs at any point in the pipeline,
    enabling save/load functionality and incremental execution.
    """

    # Pipeline inputs
    theme: str = ""
    initial_illustration_style: str | None = None  # If set, skip LLM style selection

    # Character identifiers (for reference - actual objects loaded separately)
    character_ids: List[str] = field(default_factory=list)

    # Pipeline state (stored as string for YAML serialization compatibility)
    current_step: str = PipelineStep.NOT_STARTED.value
    vision_critic_iteration: int = 0
    outline_critic_iteration: int = 0
    script_critic_iteration: int = 0
    illustration_critic_iteration: int = 0

    # Pipeline outputs - stored as dataclass instances, serialized via asdict()
    concept: ConceptIllustratedOutput | None = None
    concept_history: List[ConceptIllustratedOutput] = field(
        default_factory=list
    )  # Previous concept revisions
    prose: str | None = None  # Novel-like narrative describing the full story
    prose_history: List[str] = field(default_factory=list)  # Previous prose revisions
    page_outline: PageOutlineOutput | None = None  # Page-by-page outline
    page_outline_history: List[PageOutlineOutput] = field(
        default_factory=list
    )  # Previous outline revisions
    script: List[ScriptNode] | None = None
    script_history: List[List[ScriptNode]] = field(
        default_factory=list
    )  # Previous script revisions

    # Critic feedback history
    vision_feedback_history: List[QCFeedbackWithChecklist] = field(default_factory=list)
    prose_feedback_history: List[QCFeedbackWithChecklist] = field(default_factory=list)
    outline_feedback_history: List[QCFeedbackWithChecklist] = field(
        default_factory=list
    )
    script_feedback_history: List[QCFeedbackWithChecklist] = field(default_factory=list)
    illustration_feedback_history: List[QCFeedbackWithChecklist] = field(
        default_factory=list
    )

    # Accumulated checklists (for tracking issues across iterations)
    outline_accumulated_checklist: List[QCChecklistItem] = field(default_factory=list)
    script_accumulated_checklist: List[QCChecklistItem] = field(default_factory=list)
    illustration_accumulated_checklist: List[QCChecklistItem] = field(
        default_factory=list
    )

    # Prop sketches (generated between script and illustrations)
    prop_sketches: Dict[str, PropSketch] | None = None

    # Illustrated page outputs
    illustrated_pages: List[IllustratedScriptNode] | None = None

    # Published page outputs (with speech bubbles)
    published_pages: List[PublishedPageOutput] | None = None

    # Timing data
    timing: PipelineTiming = field(default_factory=PipelineTiming)

    # Cost data
    costs: PipelineCosts = field(default_factory=PipelineCosts)


# Type alias for progress callback
ProgressCallback = Callable[[ManagerSnapshot, str], None]


class Manager:
    """
    Orchestrates the story production pipeline.

    The manager coordinates concept generation (Director), page outline (Outline),
    script generation (Scripter), illustration (Illustrator), lettering (Letterer),
    and publishing (Publisher) with critic feedback loops at each stage.

    Supports step-based execution with snapshots for save/load and retry.
    """

    def __init__(
        self,
        config: ManagerConfig,
        snapshot: ManagerSnapshot | None = None,
        router: ModelRouter | None = None,
    ):
        """
        Initialize the manager with configuration.

        Args:
            config: Manager configuration including critic loop limits
            snapshot: Optional existing snapshot to resume from
            router: Optional ModelRouter instance to use for all API calls.
                Pass a router with default_service_tier="flex" for batch jobs.
        """
        self.config = config
        self.snapshot = snapshot or ManagerSnapshot()
        self.router = router

        # Initialize pipeline components with shared router
        self.director = Director(config.director_config, router=router)
        self.outline = Outline(config.outline_config, router=router)
        self.scripter = Scripter(config.scripter_config, router=router)

        # Downstream components (illustration_style updated at runtime via update_config)
        self.illustrator = Illustrator(config.illustrator_config)
        self.letterer = Letterer(config.letterer_config)
        self.publisher = Publisher(config.publisher_config)

        # Progress callback (called after each step)
        self._progress_callback: ProgressCallback | None = None

    def set_progress_callback(self, callback: ProgressCallback) -> None:
        """Set a callback to be invoked after each pipeline step."""
        self._progress_callback = callback

    def _notify_progress(self, step_description: str) -> None:
        """Notify the progress callback if set."""
        if self._progress_callback:
            self._progress_callback(self.snapshot, step_description)

    def _now_iso(self) -> str:
        """Get current time as ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()

    def _record_pipeline_start(self) -> None:
        """Record pipeline start time."""
        if self.snapshot.timing.pipeline_started_at is None:
            self.snapshot.timing.pipeline_started_at = self._now_iso()

    def _record_pipeline_end(self) -> None:
        """Record pipeline end time and compute duration."""
        now = self._now_iso()
        self.snapshot.timing.pipeline_completed_at = now
        if self.snapshot.timing.pipeline_started_at:
            start = datetime.fromisoformat(self.snapshot.timing.pipeline_started_at)
            end = datetime.fromisoformat(now)
            self.snapshot.timing.pipeline_duration_ms = int(
                (end - start).total_seconds() * 1000
            )

    def _record_step_start(self, step: str) -> None:
        """Record step start time."""
        self.snapshot.timing.steps[step] = StepTiming(started_at=self._now_iso())

    def _record_step_end(self, step: str) -> None:
        """Record step end time and compute duration."""
        if step not in self.snapshot.timing.steps:
            return
        now = self._now_iso()
        step_timing = self.snapshot.timing.steps[step]
        step_timing.completed_at = now
        start = datetime.fromisoformat(step_timing.started_at)
        end = datetime.fromisoformat(now)
        step_timing.duration_ms = int((end - start).total_seconds() * 1000)

    def _record_iteration_start(self, critic_type: str, iteration: int) -> None:
        """Record critic iteration start time (1-indexed)."""
        if critic_type not in self.snapshot.timing.iterations:
            self.snapshot.timing.iterations[critic_type] = []
        self.snapshot.timing.iterations[critic_type].append(
            IterationTiming(iteration=iteration, started_at=self._now_iso())
        )

    def _record_iteration_end(self, critic_type: str, iteration: int) -> None:
        """Record critic iteration end time and compute duration (1-indexed)."""
        if critic_type not in self.snapshot.timing.iterations:
            return
        for iter_timing in self.snapshot.timing.iterations[critic_type]:
            if iter_timing.iteration == iteration and iter_timing.completed_at is None:
                now = self._now_iso()
                iter_timing.completed_at = now
                start = datetime.fromisoformat(iter_timing.started_at)
                end = datetime.fromisoformat(now)
                iter_timing.duration_ms = int((end - start).total_seconds() * 1000)
                break

    def _record_step_cost(self, step: str, accumulator: StepCostAccumulator) -> None:
        """Record accumulated costs for a step."""
        self.snapshot.costs.steps[step] = StepCost(
            input_tokens=accumulator.input_tokens,
            output_tokens=accumulator.output_tokens,
            cost_usd=accumulator.cost_usd,
            call_count=accumulator.call_count,
        )
        # Update totals
        self.snapshot.costs.total_input_tokens += accumulator.input_tokens
        self.snapshot.costs.total_output_tokens += accumulator.output_tokens
        self.snapshot.costs.total_cost_usd += accumulator.cost_usd

    def get_snapshot(self) -> ManagerSnapshot:
        """Get the current pipeline snapshot."""
        return self.snapshot

    def produce_story(
        self,
        characters: List[character.Character],
        theme: str,
        initial_illustration_style: str | None = None,
    ) -> ManagerSnapshot:
        """
        Produce a story concept from input elements.

        Currently runs concept generation + concept critic, then returns.
        Downstream steps (prose, outline, script, illustrations) are pending refactor.

        Args:
            characters: List of Character objects for the story (max 2)
            theme: Central theme of the story
            initial_illustration_style: Optional pre-selected illustration style
                (one of: abstract, cartoon, line_drawing, manga, moody, realistic,
                vintage, whimsical, wimmelbuch). If provided, LLM style selection is skipped.

        Returns:
            ManagerSnapshot containing the finalized concept
        """
        if len(characters) > 2:
            raise ValueError(
                f"Maximum 2 characters allowed, but {len(characters)} were provided."
            )

        # Initialize snapshot with inputs
        self.snapshot.theme = theme
        self.snapshot.initial_illustration_style = initial_illustration_style
        self.snapshot.character_ids = [c.identifier for c in characters]

        logger.info("Starting story production pipeline")
        logger.info(f"Input: {len(characters)} characters, theme='{theme}'")

        # Run incremental pipeline
        self.run_pipeline_incremental(characters)

        logger.info("Story production complete")
        return self.snapshot

    def run_pipeline_incremental(
        self,
        characters: List[character.Character],
        stop_after_step: str | None = None,
        restart_step: bool = False,
    ) -> None:
        """
        Run the pipeline incrementally, respecting current snapshot state.

        This method can be called to resume a partially completed pipeline.

        Args:
            characters: List of Character objects for the story
            stop_after_step: Optional step value to stop after (e.g., "generate_concept")
            restart_step: If True, restart the current step fresh instead of resuming
                from previous QC state. This resets feedback history, content history,
                iteration count, and accumulated checklist for the current critic stage.
        """
        # Record pipeline start time (only if not already started)
        self._record_pipeline_start()

        def should_stop(completed_step: str) -> bool:
            """Check if we should stop after completing this step."""
            return stop_after_step is not None and completed_step == stop_after_step

        # Step 1: Generate concept if not started or resuming from failed generation
        if self.snapshot.current_step in [
            PipelineStep.NOT_STARTED.value,
            PipelineStep.GENERATE_CONCEPT.value,
        ]:
            self._step_generate_concept(characters)
            if should_stop(PipelineStep.GENERATE_CONCEPT.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 2: Optional critic concept loop
        if self.snapshot.current_step == PipelineStep.CRITIC_CONCEPT.value:
            self._step_critic_concept_loop(characters, restart_step)
            if should_stop(PipelineStep.CRITIC_CONCEPT.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 3: Illustrate concept
        if self.snapshot.current_step == PipelineStep.ILLUSTRATE_CONCEPT.value:
            self._step_illustrate_concept(characters)
            if should_stop(PipelineStep.ILLUSTRATE_CONCEPT.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 4: Generate outline
        if self.snapshot.current_step == PipelineStep.GENERATE_OUTLINE.value:
            self._step_generate_outline(characters)
            if should_stop(PipelineStep.GENERATE_OUTLINE.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 5: Optional critic outline loop
        if self.snapshot.current_step == PipelineStep.CRITIC_OUTLINE.value:
            self._step_critic_outline_loop(characters, restart_step)
            if should_stop(PipelineStep.CRITIC_OUTLINE.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 6: Generate script
        if self.snapshot.current_step == PipelineStep.GENERATE_SCRIPT.value:
            self._step_generate_script(characters)
            if should_stop(PipelineStep.GENERATE_SCRIPT.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 7: Optional critic script loop
        if self.snapshot.current_step == PipelineStep.CRITIC_SCRIPT.value:
            self._step_critic_script_loop(characters, restart_step)
            if should_stop(PipelineStep.CRITIC_SCRIPT.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 7b: Sketch key props
        if self.snapshot.current_step == PipelineStep.SKETCH_PROPS.value:
            self._step_sketch_props(characters)
            if should_stop(PipelineStep.SKETCH_PROPS.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 8: Generate illustrations (base sketch + style transfer)
        if self.snapshot.current_step == PipelineStep.GENERATE_ILLUSTRATIONS.value:
            self._step_generate_illustrations(characters)
            if should_stop(PipelineStep.GENERATE_ILLUSTRATIONS.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 9: Optional critic illustrations loop
        if self.snapshot.current_step == PipelineStep.CRITIC_ILLUSTRATIONS.value:
            self._step_critic_illustrations_loop(characters, restart_step)
            if should_stop(PipelineStep.CRITIC_ILLUSTRATIONS.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 10: Generate lettering (speech bubbles + narrator captions)
        if self.snapshot.current_step == PipelineStep.GENERATE_LETTERING.value:
            self._step_generate_lettering(characters)
            if should_stop(PipelineStep.GENERATE_LETTERING.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

        # Step 11: Generate published pages (device-specific aspect ratios)
        if self.snapshot.current_step == PipelineStep.GENERATE_PUBLISH.value:
            self._step_generate_publish(characters)
            if should_stop(PipelineStep.GENERATE_PUBLISH.value):
                logger.info(f"Stopping after step: {stop_after_step}")
                return

    def _step_generate_concept(
        self,
        characters: List[character.Character],
    ) -> None:
        """Execute the concept generation step."""
        logger.info("Step 1: Generating vision/concept")
        self.snapshot.current_step = PipelineStep.GENERATE_CONCEPT.value
        self._record_step_start(PipelineStep.GENERATE_CONCEPT.value)

        with track_step_costs(PipelineStep.GENERATE_CONCEPT.value) as cost_acc:
            concept_output = self.director.generate_concept(
                theme=self.snapshot.theme,
                characters=characters,
                initial_illustration_style=self.snapshot.initial_illustration_style,
            )

            # Wrap ConceptOutput in ConceptIllustratedOutput for snapshot storage
            self.snapshot.concept = ConceptIllustratedOutput(
                concept=concept_output,
                title_shot_prompt=None,
                title_shot_image=None,
            )
            logger.info(f"Generated concept: '{concept_output.title}'")

            # Always move to critic phase (critic loop handles skip if not configured)
            self.snapshot.current_step = PipelineStep.CRITIC_CONCEPT.value

        self._record_step_cost(PipelineStep.GENERATE_CONCEPT.value, cost_acc)
        self._record_step_end(PipelineStep.GENERATE_CONCEPT.value)
        self._notify_progress("Generated initial concept")

    def _step_critic_concept_loop(
        self,
        characters: List[character.Character],
        restart_step: bool = False,
    ) -> None:
        """Execute the concept critic feedback loop via Director.run_concept_qc."""
        assert (
            self.snapshot.concept is not None
        ), "Concept must be set before concept critic"

        # Extract ConceptOutput for QC (run_concept_qc works with ConceptOutput)
        concept = self.snapshot.concept.concept
        max_iterations = self.config.max_concept_critic_iterations

        self._record_step_start(PipelineStep.CRITIC_CONCEPT.value)

        if max_iterations <= 0:
            logger.info("No concept critics configured, skipping critic loop")
            self.snapshot.current_step = PipelineStep.ILLUSTRATE_CONCEPT.value
            return

        logger.info(f"Starting concept critic loop (max {max_iterations} iterations)")

        def on_feedback(feedback: QCFeedbackWithChecklist, iteration: int) -> None:
            self.snapshot.vision_feedback_history.append(copy.deepcopy(feedback))
            self._notify_progress(
                f"Received concept feedback (iteration {iteration + 1})"
            )

        def on_revision(new_concept: ConceptOutput, iteration: int) -> None:
            assert self.snapshot.concept is not None
            self.snapshot.concept_history.append(self.snapshot.concept)
            self.snapshot.concept = ConceptIllustratedOutput(
                concept=new_concept,
                title_shot_prompt=None,
                title_shot_image=None,
            )
            self.snapshot.vision_critic_iteration = iteration
            self._notify_progress(f"Concept critic iteration {iteration} complete")

        # Build QC state for restart recovery (None if restarting fresh)
        qc_state = None
        if not restart_step:
            qc_state = QCState(
                feedback_history=list(self.snapshot.vision_feedback_history),
                content_history=[
                    c.concept.to_json(indent=2) for c in self.snapshot.concept_history
                ],
                iteration=self.snapshot.vision_critic_iteration,
                accumulated_checklist=[],
            )
        else:
            self.snapshot.vision_feedback_history = []
            self.snapshot.concept_history = []
            self.snapshot.vision_critic_iteration = 0
            logger.info("Restarting concept critic loop fresh (cleared previous state)")

        with track_step_costs(PipelineStep.CRITIC_CONCEPT.value) as cost_acc:
            result = self.director.run_concept_qc(
                concept=concept,
                theme=self.snapshot.theme,
                characters=characters,
                initial_illustration_style=self.snapshot.initial_illustration_style,
                max_iterations=max_iterations,
                state=qc_state,
                on_feedback=on_feedback,
                on_revision=on_revision,
            )

            if not result.approved:
                logger.warning(
                    f"Concept critic loop reached max iterations ({max_iterations}) without approval"
                )
            else:
                logger.info("Concept critic approved")

        self._record_step_cost(PipelineStep.CRITIC_CONCEPT.value, cost_acc)
        self._record_step_end(PipelineStep.CRITIC_CONCEPT.value)
        self.snapshot.current_step = PipelineStep.ILLUSTRATE_CONCEPT.value
        self._notify_progress("Concept critic complete")

    def _step_illustrate_concept(
        self,
        characters: List[character.Character],
    ) -> None:
        """Generate title shot image for finalized concept and mark pipeline complete."""
        assert (
            self.snapshot.concept is not None
        ), "Concept must be set before illustration"

        logger.info("Step 3: Generating title shot image")
        self._record_step_start(PipelineStep.ILLUSTRATE_CONCEPT.value)

        with track_step_costs(PipelineStep.ILLUSTRATE_CONCEPT.value) as cost_acc:
            illustrated_concept = self.director.illustrate_concept(
                concept=self.snapshot.concept.concept,
                characters=characters,
            )
            self.snapshot.concept = illustrated_concept

        self._record_step_cost(PipelineStep.ILLUSTRATE_CONCEPT.value, cost_acc)
        self._record_step_end(PipelineStep.ILLUSTRATE_CONCEPT.value)
        self.snapshot.current_step = PipelineStep.GENERATE_OUTLINE.value
        self._notify_progress("Title shot generated")

    def _step_generate_outline(
        self,
        characters: List[character.Character],
    ) -> None:
        """Generate page-by-page outline from the finalized concept."""
        assert self.snapshot.concept is not None, "Concept must be set before outline"

        logger.info("Step 4: Generating page outline")
        self.snapshot.current_step = PipelineStep.GENERATE_OUTLINE.value
        self._record_step_start(PipelineStep.GENERATE_OUTLINE.value)

        style_enum = get_style_from_string(
            self.snapshot.concept.concept.illustration_style
        )
        shot_style_spec = SHOT_SPECS.get(style_enum, "")

        with track_step_costs(PipelineStep.GENERATE_OUTLINE.value) as cost_acc:
            outline = self.outline.generate_page_outline(
                concept=self.snapshot.concept.concept,
                characters=characters,
                illustration_style=self.snapshot.concept.concept.illustration_style,
                shot_style_spec=shot_style_spec,
            )
            self.snapshot.page_outline = outline
            logger.info(f"Generated outline with {len(outline.pages)} pages")

            self.snapshot.current_step = PipelineStep.CRITIC_OUTLINE.value

        self._record_step_cost(PipelineStep.GENERATE_OUTLINE.value, cost_acc)
        self._record_step_end(PipelineStep.GENERATE_OUTLINE.value)
        self._notify_progress("Generated page outline")

    def _step_critic_outline_loop(
        self,
        characters: List[character.Character],
        restart_step: bool = False,
    ) -> None:
        """Execute the outline critic feedback loop."""
        assert (
            self.snapshot.concept is not None
        ), "Concept must be set before outline critic"
        assert (
            self.snapshot.page_outline is not None
        ), "Outline must be set before outline critic"

        max_iterations = self.config.max_outline_critic_iterations

        self._record_step_start(PipelineStep.CRITIC_OUTLINE.value)

        if max_iterations <= 0:
            logger.info("No outline critics configured, skipping critic loop")
            self.snapshot.current_step = PipelineStep.GENERATE_SCRIPT.value
            return

        logger.info(f"Starting outline critic loop (max {max_iterations} iterations)")

        def on_feedback(feedback: QCFeedbackWithChecklist, iteration: int) -> None:
            self.snapshot.outline_feedback_history.append(copy.deepcopy(feedback))
            self._notify_progress(
                f"Received outline feedback (iteration {iteration + 1})"
            )

        def on_revision(new_outline: PageOutlineOutput, iteration: int) -> None:
            assert self.snapshot.page_outline is not None
            self.snapshot.page_outline_history.append(self.snapshot.page_outline)
            self.snapshot.page_outline = new_outline
            self.snapshot.outline_critic_iteration = iteration
            self._notify_progress(f"Outline critic iteration {iteration} complete")

        qc_state = None
        if not restart_step:
            qc_state = QCState(
                feedback_history=list(self.snapshot.outline_feedback_history),
                content_history=[
                    o.to_json(indent=2) for o in self.snapshot.page_outline_history
                ],
                iteration=self.snapshot.outline_critic_iteration,
                accumulated_checklist=[],
            )
        else:
            self.snapshot.outline_feedback_history = []
            self.snapshot.page_outline_history = []
            self.snapshot.outline_critic_iteration = 0
            logger.info("Restarting outline critic loop fresh (cleared previous state)")

        style_enum = get_style_from_string(
            self.snapshot.concept.concept.illustration_style
        )
        shot_style_spec = SHOT_SPECS.get(style_enum, "")

        with track_step_costs(PipelineStep.CRITIC_OUTLINE.value) as cost_acc:
            result = self.outline.run_outline_qc(
                outline=self.snapshot.page_outline,
                concept=self.snapshot.concept.concept,
                characters=characters,
                age_range=self.config.director_config.audience_age_range,
                illustration_style=self.snapshot.concept.concept.illustration_style,
                shot_style_spec=shot_style_spec,
                max_iterations=max_iterations,
                state=qc_state,
                on_feedback=on_feedback,
                on_revision=on_revision,
            )

            if not result.approved:
                logger.warning(
                    f"Outline critic loop reached max iterations ({max_iterations}) without approval"
                )
            else:
                logger.info("Outline critic approved")

        self._record_step_cost(PipelineStep.CRITIC_OUTLINE.value, cost_acc)
        self._record_step_end(PipelineStep.CRITIC_OUTLINE.value)
        self.snapshot.current_step = PipelineStep.GENERATE_SCRIPT.value
        self._notify_progress("Outline finalized")

    def _step_generate_script(
        self,
        characters: List[character.Character],
    ) -> None:
        """Generate script from the finalized page outline."""
        assert self.snapshot.concept is not None, "Concept must be set before script"
        assert (
            self.snapshot.page_outline is not None
        ), "Outline must be set before script"

        logger.info("Step 6: Generating script")
        self.snapshot.current_step = PipelineStep.GENERATE_SCRIPT.value
        self._record_step_start(PipelineStep.GENERATE_SCRIPT.value)

        with track_step_costs(PipelineStep.GENERATE_SCRIPT.value) as cost_acc:
            script_nodes = self.scripter.prepare_story(
                page_outline=self.snapshot.page_outline,
                characters=characters,
                director_vision=self.snapshot.concept.concept,
            )
            self.snapshot.script = script_nodes
            logger.info(f"Generated script with {len(script_nodes)} pages")

            self.snapshot.current_step = PipelineStep.CRITIC_SCRIPT.value

        self._record_step_cost(PipelineStep.GENERATE_SCRIPT.value, cost_acc)
        self._record_step_end(PipelineStep.GENERATE_SCRIPT.value)
        self._notify_progress("Generated script")

    def _step_critic_script_loop(
        self,
        characters: List[character.Character],
        restart_step: bool = False,
    ) -> None:
        """Execute the script critic feedback loop."""
        assert (
            self.snapshot.concept is not None
        ), "Concept must be set before script critic"
        assert (
            self.snapshot.page_outline is not None
        ), "Outline must be set before script critic"
        assert (
            self.snapshot.script is not None
        ), "Script must be set before script critic"

        max_iterations = self.config.max_script_critic_iterations

        self._record_step_start(PipelineStep.CRITIC_SCRIPT.value)

        if max_iterations <= 0:
            logger.info("No script critics configured, skipping critic loop")
            self.snapshot.current_step = PipelineStep.SKETCH_PROPS.value
            return

        logger.info(f"Starting script critic loop (max {max_iterations} iterations)")

        def on_feedback(feedback: QCFeedbackWithChecklist, iteration: int) -> None:
            self.snapshot.script_feedback_history.append(copy.deepcopy(feedback))
            self._notify_progress(
                f"Received script feedback (iteration {iteration + 1})"
            )

        def on_revision(new_script: List[ScriptNode], iteration: int) -> None:
            assert self.snapshot.script is not None
            self.snapshot.script_history.append(self.snapshot.script)
            self.snapshot.script = new_script
            self.snapshot.script_critic_iteration = iteration
            self._notify_progress(f"Script critic iteration {iteration} complete")

        qc_state = None
        if not restart_step:
            qc_state = QCState(
                feedback_history=list(self.snapshot.script_feedback_history),
                content_history=[
                    ScriptOutput(pages=s).to_json(indent=2)
                    for s in self.snapshot.script_history
                ],
                iteration=self.snapshot.script_critic_iteration,
                accumulated_checklist=list(self.snapshot.script_accumulated_checklist),
            )
        else:
            self.snapshot.script_feedback_history = []
            self.snapshot.script_history = []
            self.snapshot.script_critic_iteration = 0
            self.snapshot.script_accumulated_checklist = []
            logger.info("Restarting script critic loop fresh (cleared previous state)")

        # Build context for the general (GlobalSolve) critic
        character_str = [
            char.prompt_data.capability_prompt[Capability.TEXT] for char in characters
        ]

        style_enum = get_style_from_string(
            self.snapshot.concept.concept.illustration_style
        )
        shot_style_spec = SHOT_SPECS.get(style_enum, "")

        def build_context(checklist: List[QCChecklistItem], iter_num: int) -> str:
            return templates.render_text("script/review.context",
                age_range=self.config.director_config.audience_age_range,
                page_outline=self.snapshot.page_outline.to_json(indent=2),
                characters=character_str,
                illustration_style=self.snapshot.concept.concept.illustration_style,
                shot_style_spec=shot_style_spec,
                previous_checklist=checklist or "None",
                current_iteration=iter_num,
                max_iterations=max_iterations,
            )

        control_guide = templates.render("script/review.system")

        with track_step_costs(PipelineStep.CRITIC_SCRIPT.value) as cost_acc:
            result = self.scripter.run_script_qc(
                script=self.snapshot.script,
                page_outline=self.snapshot.page_outline,
                characters=characters,
                director_vision=self.snapshot.concept.concept,
                control_guide=control_guide,
                build_context=build_context,
                max_iterations=max_iterations,
                state=qc_state,
                on_feedback=on_feedback,
                on_revision=on_revision,
            )

            if not result.approved:
                logger.warning(
                    f"Script critic loop reached max iterations ({max_iterations}) without approval"
                )
            else:
                logger.info("Script critic approved")

        self._record_step_cost(PipelineStep.CRITIC_SCRIPT.value, cost_acc)
        self._record_step_end(PipelineStep.CRITIC_SCRIPT.value)
        self.snapshot.current_step = PipelineStep.SKETCH_PROPS.value
        self._notify_progress("Script finalized")

    def _step_sketch_props(
        self,
        characters: List[character.Character],
    ) -> None:
        """Extract key props from the script and generate reference images."""
        assert self.snapshot.concept is not None, "Concept must be set before sketch props"
        assert self.snapshot.script is not None, "Script must be set before sketch props"

        logger.info("Step: Extracting and sketching key props")
        self.snapshot.current_step = PipelineStep.SKETCH_PROPS.value
        self._record_step_start(PipelineStep.SKETCH_PROPS.value)

        illustration_style = self.snapshot.concept.concept.illustration_style
        self.illustrator.update_config(illustration_style=illustration_style)

        with track_step_costs(PipelineStep.SKETCH_PROPS.value) as cost_acc:
            self.snapshot.prop_sketches = self.illustrator.extract_props_from_script(
                script_nodes=self.snapshot.script,
                characters=characters,
            )
            logger.info(
                f"Generated {len(self.snapshot.prop_sketches)} prop sketches"
            )

        self._record_step_cost(PipelineStep.SKETCH_PROPS.value, cost_acc)
        self._record_step_end(PipelineStep.SKETCH_PROPS.value)
        self.snapshot.current_step = PipelineStep.GENERATE_ILLUSTRATIONS.value
        self._notify_progress("Prop sketches complete")

    def _step_generate_illustrations(
        self,
        characters: List[character.Character],
    ) -> None:
        """Generate base sketch and styled illustration for each script page."""
        assert self.snapshot.concept is not None, "Concept must be set before illustrations"
        assert self.snapshot.script is not None, "Script must be set before illustrations"

        logger.info("Step: Generating page illustrations")
        self.snapshot.current_step = PipelineStep.GENERATE_ILLUSTRATIONS.value
        self._record_step_start(PipelineStep.GENERATE_ILLUSTRATIONS.value)

        illustration_style = self.snapshot.concept.concept.illustration_style
        self.illustrator.update_config(illustration_style=illustration_style)

        # Use title shot as style reference
        style_reference = self.snapshot.concept.title_shot_image

        # Prepare prop data from sketch_props step
        key_props = (
            {name: ps.visual_description for name, ps in self.snapshot.prop_sketches.items()}
            if self.snapshot.prop_sketches else None
        )
        prop_sketch_images = (
            {name: ps.image for name, ps in self.snapshot.prop_sketches.items()}
            if self.snapshot.prop_sketches else None
        )

        illustrated_pages: List[IllustratedScriptNode] = []

        with track_step_costs(PipelineStep.GENERATE_ILLUSTRATIONS.value) as cost_acc:
            for idx, node in enumerate(self.snapshot.script):
                logger.info(
                    f"Page {node.page} ({idx + 1}/{len(self.snapshot.script)}): "
                    "Generating illustration"
                )

                try:
                    # Generate base sketch
                    sketch = self.illustrator.sketch_page(
                        shot=node.shot,
                        characters=characters,
                        key_props=key_props,
                        prop_sketches=prop_sketch_images,
                    )

                    # Apply style transfer
                    styled = self.illustrator.style_page(
                        base_image=sketch.image,
                        style_reference_override=style_reference,
                    )

                    illustrated_pages.append(
                        IllustratedScriptNode(
                            node=node,
                            status="completed",
                            image_url=sketch.image,
                            image_prompt=sketch.prompt,
                            styled_image_url=styled.image,
                            styled_image_prompt=styled.prompt,
                            matched_character_names=sketch.matched_character_names,
                            matched_prop_names=sketch.matched_prop_names,
                        )
                    )
                except Exception as e:
                    logger.error(f"Page {node.page}: Error generating illustration: {e}")
                    illustrated_pages.append(
                        IllustratedScriptNode(
                            node=node,
                            status="error",
                            error=str(e),
                        )
                    )

                # Save progress after each page
                self.snapshot.illustrated_pages = illustrated_pages
                self._notify_progress(f"Illustrated page {node.page}")

        self._record_step_cost(PipelineStep.GENERATE_ILLUSTRATIONS.value, cost_acc)
        self._record_step_end(PipelineStep.GENERATE_ILLUSTRATIONS.value)
        self.snapshot.current_step = PipelineStep.CRITIC_ILLUSTRATIONS.value
        self._notify_progress("All illustrations generated")

    def _step_critic_illustrations_loop(
        self,
        characters: List[character.Character],
        restart_step: bool = False,
    ) -> None:
        """Execute the illustration critic feedback loop."""
        assert (
            self.snapshot.concept is not None
        ), "Concept must be set before illustration critic"
        assert (
            self.snapshot.page_outline is not None
        ), "Outline must be set before illustration critic"
        assert (
            self.snapshot.illustrated_pages is not None
        ), "Illustrated pages must be set before illustration critic"

        max_iterations = self.config.max_illustration_critic_iterations

        self._record_step_start(PipelineStep.CRITIC_ILLUSTRATIONS.value)

        if max_iterations <= 0:
            logger.info("No illustration critics configured, skipping critic loop")
            self.snapshot.current_step = PipelineStep.GENERATE_LETTERING.value
            return

        logger.info(
            f"Starting illustration critic loop (max {max_iterations} iterations)"
        )

        if restart_step:
            self.snapshot.illustration_feedback_history = []
            self.snapshot.illustration_critic_iteration = 0
            logger.info("Restarting illustration critic loop fresh")

        illustration_style = self.snapshot.concept.concept.illustration_style
        self.illustrator.update_config(illustration_style=illustration_style)

        style_reference = self.snapshot.concept.title_shot_image

        # Prepare prop data for critique and revision
        key_props = (
            {name: ps.visual_description for name, ps in self.snapshot.prop_sketches.items()}
            if self.snapshot.prop_sketches else None
        )
        prop_sketch_images = (
            {name: ps.image for name, ps in self.snapshot.prop_sketches.items()}
            if self.snapshot.prop_sketches else None
        )

        def on_feedback(feedback: QCFeedbackWithChecklist, iteration: int) -> None:
            self.snapshot.illustration_feedback_history.append(
                copy.deepcopy(feedback)
            )
            self._notify_progress(
                f"Received illustration feedback (iteration {iteration + 1})"
            )

        def on_revision(
            revised_pages: List[IllustratedScriptNode], iteration: int
        ) -> None:
            self.snapshot.illustrated_pages = revised_pages
            self.snapshot.illustration_critic_iteration = iteration + 1
            self._notify_progress(
                f"Illustration revision {iteration + 1} complete"
            )

        def on_triage(
            selections: Dict[str, List[str]], iteration: int
        ) -> None:
            if self.snapshot.illustration_feedback_history:
                self.snapshot.illustration_feedback_history[-1].page_triage_selections = selections

        with track_step_costs(PipelineStep.CRITIC_ILLUSTRATIONS.value) as cost_acc:
            revised_pages, result = self.illustrator.run_illustration_qc(
                illustrated_pages=self.snapshot.illustrated_pages,
                page_outlines=self.snapshot.page_outline.pages,
                characters=characters,
                prop_sketches=prop_sketch_images,
                key_props=key_props,
                style_reference_override=style_reference,
                max_iterations=max_iterations,
                on_feedback=on_feedback,
                on_revision=on_revision,
                on_triage=on_triage,
            )

            self.snapshot.illustrated_pages = revised_pages

            if not result.approved:
                logger.warning(
                    f"Illustration critic loop reached max iterations "
                    f"({max_iterations}) without approval"
                )
            else:
                logger.info("Illustration critic approved")

        self._record_step_cost(PipelineStep.CRITIC_ILLUSTRATIONS.value, cost_acc)
        self._record_step_end(PipelineStep.CRITIC_ILLUSTRATIONS.value)
        self.snapshot.current_step = PipelineStep.GENERATE_LETTERING.value
        self._notify_progress("Illustration critique complete")

    def _step_generate_lettering(
        self,
        characters: List[character.Character],
    ) -> None:
        """Add speech bubbles and narrator captions to illustrated pages."""
        assert (
            self.snapshot.concept is not None
        ), "Concept must be set before lettering"
        assert (
            self.snapshot.illustrated_pages is not None
        ), "Illustrated pages must be set before lettering"

        logger.info("Step: Generating lettering")
        self.snapshot.current_step = PipelineStep.GENERATE_LETTERING.value
        self._record_step_start(PipelineStep.GENERATE_LETTERING.value)

        illustration_style = self.snapshot.concept.concept.illustration_style
        self.letterer.update_config(illustration_style=illustration_style)

        with track_step_costs(PipelineStep.GENERATE_LETTERING.value) as cost_acc:
            # Letter the title page
            if (
                self.snapshot.concept.title_shot_image
            ):
                logger.info("Lettering title page")
                try:
                    lettered_title, lettered_title_prompt = (
                        self.letterer.letter_title_page(
                            title_shot_image=self.snapshot.concept.title_shot_image,
                            title=self.snapshot.concept.concept.title,
                        )
                    )
                    self.snapshot.concept.lettered_title_image = lettered_title
                    self.snapshot.concept.lettered_title_prompt = lettered_title_prompt
                    self._notify_progress("Lettered title page")
                except Exception as e:
                    logger.error(f"Error lettering title page: {e}")

            for idx, illustrated_node in enumerate(self.snapshot.illustrated_pages):
                if not self.letterer.has_lettering_content(illustrated_node):
                    logger.info(
                        f"Page {illustrated_node.node.page}: "
                        "No lettering content, skipping"
                    )
                    continue

                logger.info(
                    f"Page {illustrated_node.node.page} "
                    f"({idx + 1}/{len(self.snapshot.illustrated_pages)}): "
                    "Adding lettering"
                )

                try:
                    lettered_image, lettered_prompt = self.letterer.letter_page(illustrated_node)
                    illustrated_node.lettered_image_url = lettered_image
                    illustrated_node.lettered_image_prompt = lettered_prompt
                except Exception as e:
                    logger.error(
                        f"Page {illustrated_node.node.page}: "
                        f"Error adding lettering: {e}"
                    )

                self._notify_progress(
                    f"Lettered page {illustrated_node.node.page}"
                )

        self._record_step_cost(PipelineStep.GENERATE_LETTERING.value, cost_acc)
        self._record_step_end(PipelineStep.GENERATE_LETTERING.value)
        self.snapshot.current_step = PipelineStep.GENERATE_PUBLISH.value
        self._notify_progress("Lettering complete")

    def _step_generate_publish(
        self,
        characters: List[character.Character],
    ) -> None:
        """Generate device-specific aspect ratio images for each page."""
        assert (
            self.snapshot.concept is not None
        ), "Concept must be set before publishing"
        assert (
            self.snapshot.illustrated_pages is not None
        ), "Illustrated pages must be set before publishing"

        logger.info("Step: Generating published pages")
        self.snapshot.current_step = PipelineStep.GENERATE_PUBLISH.value
        self._record_step_start(PipelineStep.GENERATE_PUBLISH.value)

        illustration_style = self.snapshot.concept.concept.illustration_style
        self.publisher.update_config(illustration_style=illustration_style)

        published_pages: List[PublishedPageOutput] = []

        with track_step_costs(PipelineStep.GENERATE_PUBLISH.value) as cost_acc:
            # Publish the title page (device-specific variants)
            if self.snapshot.concept.lettered_title_image:
                logger.info("Publishing title page (iPad + iPhone)")
                try:
                    ipad_title, iphone_title = self.publisher.publish_title(
                        lettered_title_image=self.snapshot.concept.lettered_title_image,
                    )
                    self.snapshot.concept.published_title_ipad_image = ipad_title
                    self.snapshot.concept.published_title_iphone_image = iphone_title
                    self._notify_progress("Published title page")
                except Exception as e:
                    logger.error(f"Error publishing title page: {e}")

            for idx, illustrated_node in enumerate(self.snapshot.illustrated_pages):
                logger.info(
                    f"Page {illustrated_node.node.page} "
                    f"({idx + 1}/{len(self.snapshot.illustrated_pages)}): Publishing"
                )

                try:
                    published = self.publisher.publish_page(illustrated_node)
                    published_pages.append(published)
                except Exception as e:
                    logger.error(
                        f"Page {illustrated_node.node.page}: "
                        f"Error publishing: {e}"
                    )
                    published_pages.append(
                        PublishedPageOutput(
                            illustrated_node=illustrated_node,
                            status="error",
                            error=str(e),
                        )
                    )

                self.snapshot.published_pages = published_pages
                self._notify_progress(
                    f"Published page {illustrated_node.node.page}"
                )

        self._record_step_cost(PipelineStep.GENERATE_PUBLISH.value, cost_acc)
        self._record_step_end(PipelineStep.GENERATE_PUBLISH.value)
        self.snapshot.current_step = PipelineStep.COMPLETED.value
        self._record_pipeline_end()
        self._notify_progress("Publishing complete")
