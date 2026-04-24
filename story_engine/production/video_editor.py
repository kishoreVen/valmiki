
"""
VideoEditor module for scene/shot enhancement and video generation.

Provides LLM-powered enhancement of user-provided scene and shot descriptions,
opening frame generation, and sequential video compilation with last-frame
chaining between shots.
"""

import base64
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from PIL import Image

from story_engine.lib.model_router.model_interface import (
    Query,
    Capability,
    ImageGenQuery,
    VideoGenQuery,
)
from story_engine.lib.model_router.router import ModelRouter
from story_engine.lib.model_router.retry import RetryConfig
from story_engine.lib.quality_control.playbooks.global_solve import GlobalSolveConfig
from story_engine.lib.quality_control.pipeline import QualityControlPipeline
from story_engine.lib.quality_control.types import (
    CritiqueRequest,
    QCFeedbackWithChecklist,
    QualityControlConfig,
)
from story_engine.elements.character import Character
from story_engine.lib import output_formatting
from story_engine.lib.video_utils import extract_last_frame
from story_engine.production.template_registry import templates
from story_engine.lib.local_storage import upload_video, upload_image, get_signed_url


logger = logging.getLogger(__name__)


@dataclass
class VideoEditorConfig:
    """Configuration for the VideoEditor."""

    # LLM interface for scene/shot enhancement
    enhancer_model_interface: str = "openai_gpt5"

    # LLM interfaces for critic loop
    critic_interfaces: list[str] = field(default_factory=lambda: ["anthropic_opus45"])

    # Max QC iterations for scene/shot enhancement
    scene_qc_iterations: int = 2
    shots_qc_iterations: int = 2

    # Image generation interface for storyboard images
    storyboard_model_interface: str = "gemini_pro3_image"

    # LLM interface for prompt compaction
    compaction_interface_type: str = "anthropic_haiku45"

    # Video generation interface
    video_model_interface: str = "runware_kling_v3"

    # Storyboard image resolution (16:9)
    storyboard_resolution: tuple[int, int] = (1024, 576)


class VideoEditor:
    """Enhances scene/shot descriptions and generates storyboard frames for video."""

    def __init__(self, config: VideoEditorConfig) -> None:
        self.config = config
        retry_config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=30.0,
            exponential_base=2.0,
        )
        self.router = ModelRouter(retry_config=retry_config)

    def enhance_scene(
        self, scene_description: str, character: Character
    ) -> str:
        """Expand a brief scene description into a detailed cinematic one.

        Args:
            scene_description: User-provided brief scene description.
            character: Character element with config and sketches.

        Returns:
            Enhanced scene description string (2-4 sentences).
        """
        input_data = json.dumps({
            "scene_description": scene_description,
            "character_visual": character.config.compact_visual_description or character.config.name,
        })

        query = Query(
            structured_prompt=templates.render("video_editor/enhance_scene.system"),
            query_text=input_data,
            repetitions=2,
        )

        response = self.router.get_response(
            query, Capability.TEXT, self.config.enhancer_model_interface
        )

        raw_text = response["text"]
        logger.info(f"enhance_scene raw response (first 500 chars): {raw_text[:500]}")
        result = output_formatting.safe_json_decode(raw_text)
        logger.info(f"enhance_scene parsed keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
        enhanced = result.get("enhanced_description", scene_description)
        if enhanced == scene_description:
            logger.warning("enhance_scene: LLM returned original (key missing or parse failed)")
        logger.info(f"Enhanced scene: {enhanced[:100]}...")
        return enhanced

    def enhance_shots(
        self,
        scene_description: str,
        shot_descriptions: List[str],
        character: Character,
        shot_durations: List[float] | None = None,
    ) -> List[str]:
        """Expand brief shot descriptions given scene context.

        Args:
            scene_description: The (enhanced) scene description for context.
            shot_descriptions: List of user-provided brief shot descriptions.
            character: Character element with config and sketches.
            shot_durations: Optional list of durations (seconds) per shot.

        Returns:
            List of enhanced shot descriptions (same count as input).
        """
        durations = shot_durations or [5.0] * len(shot_descriptions)
        input_data = json.dumps({
            "scene_description": scene_description,
            "shots": [
                {"description": desc, "duration": dur}
                for desc, dur in zip(shot_descriptions, durations)
            ],
            "character_visual": character.config.compact_visual_description or character.config.name,
        })

        query = Query(
            structured_prompt=templates.render("video_editor/enhance_shots.system"),
            query_text=input_data,
            repetitions=2,
        )

        response = self.router.get_response(
            query, Capability.TEXT, self.config.enhancer_model_interface
        )

        raw_text = response["text"]
        logger.info(f"enhance_shots raw response (first 500 chars): {raw_text[:500]}")
        result = output_formatting.safe_json_decode(raw_text)
        logger.info(f"enhance_shots parsed keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
        enhanced = result.get("enhanced_shots", shot_descriptions)
        if enhanced == shot_descriptions:
            logger.warning("enhance_shots: LLM returned originals (key missing or parse failed)")

        # Ensure we return exactly the same count
        if len(enhanced) != len(shot_descriptions):
            logger.warning(
                f"Enhanced shots count mismatch: got {len(enhanced)}, "
                f"expected {len(shot_descriptions)}. Using originals for extras."
            )
            while len(enhanced) < len(shot_descriptions):
                enhanced.append(shot_descriptions[len(enhanced)])
            enhanced = enhanced[: len(shot_descriptions)]

        for i, desc in enumerate(enhanced):
            logger.info(f"  Enhanced shot {i + 1}: {desc[:80]}...")

        return enhanced

    # -------------------------------------------------------------------------
    # Feedback decoder (shared by both QC loops)
    # -------------------------------------------------------------------------

    @staticmethod
    def _feedback_decoder(text: str, model: str) -> QCFeedbackWithChecklist:
        data = output_formatting.safe_json_decode(text)
        return QCFeedbackWithChecklist.from_flat_dict(data, model=model)

    # -------------------------------------------------------------------------
    # Scene QC (GlobalSolve, 2 iterations)
    # -------------------------------------------------------------------------

    def run_scene_qc(
        self,
        enhanced_scene: str,
        original_scene: str,
        character: Character,
        on_progress: Callable[[str], None] | None = None,
    ) -> str:
        """Run critic loop on an enhanced scene description.

        Args:
            enhanced_scene: The LLM-enhanced scene description to review.
            original_scene: The user's original scene description (for context).
            character: Character element.
            on_progress: Optional callback reporting each stage (e.g. "scene_critic_1").

        Returns:
            Revised scene description after QC iterations.
        """
        max_iters = self.config.scene_qc_iterations
        character_visual = character.config.compact_visual_description or character.config.name

        playbook_config = GlobalSolveConfig(
            max_iterations=max_iters,
            model_interfaces=self.config.critic_interfaces,
            feedback_decoder=self._feedback_decoder,
        )
        qc_config = QualityControlConfig(
            playbook="GlobalSolve",
            playbook_config=playbook_config,
        )

        context = templates.render_text("video_editor/review_scene.context",
            character_visual=character_visual,
            original_scene=original_scene,
            previous_checklist="None",
            current_iteration=0,
            max_iterations=max_iters,
        )

        current_enhanced = enhanced_scene

        def revise_fn(content: str, feedback: QCFeedbackWithChecklist) -> str:
            nonlocal current_enhanced
            revise_input = json.dumps({
                "enhanced_description": content,
                "feedback": feedback.feedback.feedback,
            })
            query = Query(
                structured_prompt=templates.render("video_editor/revise_scene.system"),
                query_text=revise_input,
                repetitions=2,
            )
            response = self.router.get_response(
                query, Capability.TEXT, self.config.enhancer_model_interface
            )
            result = output_formatting.safe_json_decode(response["text"])
            current_enhanced = result.get("enhanced_description", content)
            return current_enhanced

        def on_feedback(feedback: QCFeedbackWithChecklist, iteration: int) -> None:
            if on_progress:
                on_progress(f"scene_critic_{iteration + 1}")

        qc = QualityControlPipeline(config=qc_config, router=self.router)
        qc_result = qc.run(
            request=CritiqueRequest(
                content=enhanced_scene,
                context=context,
                control_guide=templates.render("video_editor/review_scene.system"),
            ),
            revise_fn=revise_fn,
            on_feedback=on_feedback,
        )

        logger.info(
            f"Scene QC: {'approved' if qc_result.approved else 'max iterations'} "
            f"after {qc_result.iterations} iteration(s)"
        )
        return qc_result.content

    # -------------------------------------------------------------------------
    # Shots QC (GlobalSolve, 2 iterations)
    # -------------------------------------------------------------------------

    def run_shots_qc(
        self,
        enhanced_shots: List[str],
        scene_description: str,
        character: Character,
        shot_durations: List[float] | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> List[str]:
        """Run critic loop on enhanced shot descriptions.

        Args:
            enhanced_shots: The LLM-enhanced shot descriptions to review.
            scene_description: Scene description for context.
            character: Character element.
            shot_durations: Optional list of durations (seconds) per shot.
            on_progress: Optional callback reporting each stage (e.g. "shots_critic_1").

        Returns:
            Revised shot descriptions after QC iterations.
        """
        max_iters = self.config.shots_qc_iterations
        character_visual = character.config.compact_visual_description or character.config.name
        durations = shot_durations or [5.0] * len(enhanced_shots)
        num_shots = len(enhanced_shots)

        playbook_config = GlobalSolveConfig(
            max_iterations=max_iters,
            model_interfaces=self.config.critic_interfaces,
            feedback_decoder=self._feedback_decoder,
        )
        qc_config = QualityControlConfig(
            playbook="GlobalSolve",
            playbook_config=playbook_config,
        )

        context = templates.render_text("video_editor/review_shots.context",
            character_visual=character_visual,
            scene_description=scene_description,
            shot_durations=", ".join(f"{d}s" for d in durations),
            previous_checklist="None",
            current_iteration=0,
            max_iterations=max_iters,
        )

        # Content is the JSON array of shots
        content = json.dumps({"enhanced_shots": enhanced_shots})

        def revise_fn(content_str: str, feedback: QCFeedbackWithChecklist) -> str:
            revise_input = json.dumps({
                "enhanced_shots": json.loads(content_str).get("enhanced_shots", []),
                "feedback": feedback.feedback.feedback,
            })
            query = Query(
                structured_prompt=templates.render("video_editor/revise_shots.system"),
                query_text=revise_input,
                repetitions=2,
            )
            response = self.router.get_response(
                query, Capability.TEXT, self.config.enhancer_model_interface
            )
            result = output_formatting.safe_json_decode(response["text"])
            revised = result.get("enhanced_shots", [])
            # Ensure count matches
            while len(revised) < num_shots:
                revised.append(enhanced_shots[len(revised)])
            revised = revised[:num_shots]
            return json.dumps({"enhanced_shots": revised})

        def on_feedback(_feedback: QCFeedbackWithChecklist, iteration: int) -> None:
            if on_progress:
                on_progress(f"shots_critic_{iteration + 1}")

        qc = QualityControlPipeline(config=qc_config, router=self.router)
        qc_result = qc.run(
            request=CritiqueRequest(
                content=content,
                context=context,
                control_guide=templates.render("video_editor/review_shots.system"),
            ),
            revise_fn=revise_fn,
            on_feedback=on_feedback,
        )

        logger.info(
            f"Shots QC: {'approved' if qc_result.approved else 'max iterations'} "
            f"after {qc_result.iterations} iteration(s)"
        )

        final = output_formatting.safe_json_decode(qc_result.content)
        return final.get("enhanced_shots", enhanced_shots)

    def generate_opening_frame_prompt(
        self,
        scene_description: str,
        first_shot_description: str,
        character: Character,
    ) -> str:
        """Use an LLM to craft an image generation prompt for the opening frame.

        Args:
            scene_description: Enhanced scene description.
            first_shot_description: Description of the first shot.
            character: Character element with config and sketches.

        Returns:
            Image generation prompt string.
        """
        character_visual = character.config.compact_visual_description or character.config.name
        input_data = json.dumps({
            "scene_description": scene_description,
            "first_shot_description": first_shot_description,
            "character_name": character.config.name,
            "character_visual": character_visual,
        })

        query = Query(
            structured_prompt=templates.render("video_editor/generate_opening_frame.system"),
            query_text=input_data,
            repetitions=2,
        )

        response = self.router.get_response(
            query, Capability.TEXT, self.config.enhancer_model_interface
        )

        result = output_formatting.safe_json_decode(response["text"])
        image_prompt = result.get("image_prompt", "")

        if not image_prompt:
            # Fallback: simple concatenation
            image_prompt = (
                f"{character_visual} in {scene_description}. "
                f"{first_shot_description}. "
                f"Children's storybook illustration, bright saturated colors, soft edges."
            )
            logger.warning("generate_opening_frame_prompt: LLM returned empty, using fallback")

        logger.info(f"  Opening frame prompt: {image_prompt[:120]}...")
        return image_prompt

    def generate_opening_frame(
        self,
        scene_description: str,
        first_shot_description: str,
        character: Character,
    ) -> tuple[str, str]:
        """Generate a single opening keyframe image for the scene.

        Uses an LLM to craft the image prompt, then generates the image
        using the character's reference sketch for visual consistency.

        Args:
            scene_description: Enhanced scene description.
            first_shot_description: Description of the first shot.
            character: Character element with config and sketches.

        Returns:
            Tuple of (base64 encoded image, image prompt used).
        """
        # LLM pass to generate a proper image prompt
        image_prompt = self.generate_opening_frame_prompt(
            scene_description, first_shot_description, character
        )

        # Pass character sketch as named reference image (same as Illustrator)
        reference_images: Dict[str, Image] = {}
        if character.sketches:
            reference_images[character.config.name] = character.sketches[0]

        image_query = ImageGenQuery(
            query_text=image_prompt,
            image_resolution=self.config.storyboard_resolution,
            images=reference_images if reference_images else None,
            compaction_prompt=templates.render("illustrator/compact_prompt.system").to_flat_prompt(),
            compaction_model=self.config.compaction_interface_type,
            repetitions=2,
        )

        response = self.router.get_response(
            image_query,
            Capability.IMAGE_GEN,
            self.config.storyboard_model_interface,
        )

        frame_b64 = response["images"][0]
        logger.info("  Generated opening frame")
        return frame_b64, image_prompt

    def compile_scene(
        self,
        scene_id: str,
        shots: List[Dict[str, str]],
        opening_frame: Image.Image,
        character: Character,
        on_shot_complete: Callable[[str, str], None] | None = None,
    ) -> List[Dict[str, Any]]:
        """Generate videos for all shots using last-frame chaining.

        The first shot uses the opening frame as its seed image. Each
        subsequent shot uses the last frame extracted from the previous
        shot's video as its seed. No tail_image is used.

        Args:
            scene_id: Scene identifier (for storage paths).
            shots: List of dicts with 'id', 'description', and 'duration' keys.
            opening_frame: PIL Image for the first shot's seed.
            character: Character element with config and sketches.
            on_shot_complete: Optional callback(shot_id, video_url).

        Returns:
            List of dicts with 'id' and 'video_url' keys.
        """
        character_visual = character.config.compact_visual_description or character.config.name
        compiled_shots = []
        next_seed: Image.Image = opening_frame

        for shot in shots:
            shot_id = shot["id"]
            description = shot.get("description", "").strip()

            if not description:
                compiled_shots.append({"id": shot_id, "video_url": None})
                continue

            try:
                prompt = f"{character_visual}. {description}"
                duration = float(shot.get("duration", 5.0))

                video_query = VideoGenQuery(
                    query_text=prompt,
                    seed_image=next_seed,
                    tail_image=None,
                    duration=duration,
                    aspect_ratio="16:9",
                    negative_prompt="blurry, low quality, distorted",
                    generate_audio=True,
                )

                response = self.router.get_response(
                    video_query,
                    Capability.VIDEO_GEN,
                    self.config.video_model_interface,
                )

                videos = response.get("videos", [])
                if not videos or "base64" not in videos[0]:
                    raise ValueError("No video base64 in response")

                video_b64 = videos[0]["base64"]
                video_bytes = base64.b64decode(video_b64)

                # Extract last frame for the next shot's seed before uploading
                next_seed = extract_last_frame(video_bytes)

                # Upload to Firebase Storage
                storage_path = (
                    f"video_projects/{scene_id}/{uuid.uuid4().hex}.mp4"
                )
                upload_video(video_bytes, storage_path)
                video_url = get_signed_url(storage_path)

                logger.info(
                    f"  Shot {shot_id}: generated and uploaded "
                    f"({len(video_bytes):,} bytes)"
                )

                compiled_shots.append({"id": shot_id, "video_url": video_url})

                if on_shot_complete:
                    on_shot_complete(shot_id, video_url)

            except Exception as e:
                logger.error(f"  Shot {shot_id} failed: {e}")
                compiled_shots.append({"id": shot_id, "video_url": None})

        return compiled_shots

    def upload_opening_frame(self, scene_id: str, frame_b64: str) -> str:
        """Upload the opening frame to Firebase Storage.

        Args:
            scene_id: Scene identifier for storage path.
            frame_b64: Base64 encoded image.

        Returns:
            Signed URL for the uploaded image.
        """
        img_bytes = base64.b64decode(frame_b64)
        storage_path = f"video_projects/{scene_id}/opening_frame.png"
        upload_image(img_bytes, storage_path)
        url = get_signed_url(storage_path)
        logger.info("  Uploaded opening frame")
        return url
