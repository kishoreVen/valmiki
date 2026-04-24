
from dataclasses import dataclass, asdict
import base64
import json
import uuid
from typing import Any, Callable, Dict, List
from PIL import Image
from story_engine.lib.model_router.model_interface import Query, Capability, ImageGenQuery, VideoGenQuery
from story_engine.lib.model_router.router import ModelRouter
from story_engine.lib.model_router.retry import RetryConfig
from story_engine.elements import character
from story_engine.lib import output_formatting
from story_engine.lib.video_utils import extract_last_frame
from story_engine.production.template_registry import templates
from story_engine.lib.local_storage import upload_video, get_signed_url

import logging

logger = logging.getLogger(__name__)


@dataclass
class CharacterDesignerConfig:
    model_interface: str = "openai_gpt5"

    sketch_compact_model_interface: str = "openai_gpt4o_mini"

    sketch_model_interface: str = "gemini_nano_banana"

    generation_description_interface: str = "gemini_flash3"

    video_model_interface: str = "runware_kling_v3"

    # Multi-view configuration for 2D to 3D reconstruction
    num_character_views: int = 4  # Min: 1, Max: 16

    # View options that can be sampled from for 2D to 3D reconstruction:
    # - "front": Direct frontal view
    # - "back": Direct rear view
    # - "left_profile": Left side profile (90°)
    # - "right_profile": Right side profile (90°)
    # - "front_left_quarter": 45° between front and left
    # - "front_right_quarter": 45° between front and right
    # - "back_left_quarter": 45° between back and left
    # - "back_right_quarter": 45° between back and right
    # - "top_down": Bird's eye view from above
    # - "bottom_up": Worm's eye view from below
    # - "front_left_high": 45° horizontal, 30° vertical elevation
    # - "front_right_high": 45° horizontal, 30° vertical elevation
    # - "back_left_high": 135° horizontal, 30° vertical elevation
    # - "back_right_high": -135° horizontal, 30° vertical elevation
    # - "left_low": Left side with slight low angle
    # - "right_low": Right side with slight low angle
    character_views: List[str] | None = None  # Will be initialized in __post_init__

    def __post_init__(self):
        # Validate num_character_views
        if self.num_character_views < 1:
            self.num_character_views = 1
        elif self.num_character_views > 16:
            self.num_character_views = 16

        # Default views if not specified
        if self.character_views is None:
            if self.num_character_views == 1:
                self.character_views = ["front"]
            elif self.num_character_views == 2:
                self.character_views = ["front", "back"]
            elif self.num_character_views == 4:
                self.character_views = [
                    "front",
                    "back",
                    "left_profile",
                    "right_profile",
                ]
            elif self.num_character_views == 8:
                self.character_views = [
                    "front",
                    "back",
                    "left_profile",
                    "right_profile",
                    "front_left_quarter",
                    "front_right_quarter",
                    "back_left_quarter",
                    "back_right_quarter",
                ]
            else:
                # For other numbers, sample proportionally from available views
                all_views = [
                    "front",
                    "back",
                    "left_profile",
                    "right_profile",
                    "front_left_quarter",
                    "front_right_quarter",
                    "back_left_quarter",
                    "back_right_quarter",
                    "top_down",
                    "bottom_up",
                    "front_left_high",
                    "front_right_high",
                    "back_left_high",
                    "back_right_high",
                    "left_low",
                    "right_low",
                ]
                self.character_views = all_views[: self.num_character_views]


class CharacterDesigner:
    def __init__(self, config: CharacterDesignerConfig):
        self.config = config
        # Use more aggressive retry config for image generation which can be flaky
        retry_config = RetryConfig(
            max_retries=5,  # Increased from default 3
            base_delay=2.0,  # Increased from default 1.0
            max_delay=30.0,  # Increased from default 60.0
            exponential_base=2.0,  # Standard exponential backoff
        )
        self.router = ModelRouter(retry_config=retry_config)

    def _get_available_information_from_config(
        self, brief_character: character.CharacterConfig
    ) -> str:
        info = {
            "identifier": brief_character.identifier,
            "name": brief_character.name,
        }

        remaining_info = asdict(brief_character)
        del remaining_info["identifier"]
        del remaining_info["name"]

        for key, value in remaining_info.items():
            if value:
                info[key] = value

        return json.dumps(info)

    def flesh_out_character(
        self, brief_character: character.CharacterConfig
    ) -> character.CharacterConfig:
        query = Query(
            structured_prompt=templates.render("character/expand.system"),
            query_text="Available Information: "
            + self._get_available_information_from_config(brief_character),
            repetitions=2,
        )
        response = self.router.get_response(
            query=query,
            capability=Capability.TEXT,
            interface_type=self.config.model_interface,
        )

        logger.info(f"Character Designer RAW response: {response['text']}")

        return output_formatting.safe_dataclass_decode(
            character.CharacterConfig, response["text"],
            identifier=brief_character.identifier,
        )

    def compact_visual_description(self, image: Image.Image) -> str:
        """
        Analyzes a character image and produces a 5 words or less description.

        Takes a character image (PIL Image) and uses vision model to describe
        the character's most distinctive visual features in 5 words or less.

        Args:
            image: PIL Image object of the character

        Returns:
            5 words or less description of the character's visual appearance
        """
        query = Query(
            structured_prompt=templates.render("character/compact_visual.system"),
            query_text="Describe this character in 5 words or less.",
            images=image,
            repetitions=2,
        )

        response = self.router.get_response(
            query,
            Capability.TEXT,
            self.config.generation_description_interface,
        )

        logger.info(f"Compact visual description RAW response: {response['text']}")

        # Return the raw text directly - no JSON parsing needed
        return response["text"].strip()

    def sketch_character(
        self, character_element: character.Character
    ) -> Dict[str, Dict[str, Any]]:
        """
        Works on a character element to generate sketches from multiple views using a diffusion model.
        The sketches can be used for 2D to 3D reconstruction of the character.
        Returns a dictionary with view names as keys and sketch data as values.
        """
        visual_prompt = character_element.prompt_data.capability_prompt[
            Capability.IMAGE_GEN
        ]

        sketches = {}

        # Prepare the compaction query with character details and view angle
        compaction_input = {
            "backstory": character_element.config.backstory,
            "visual_description": visual_prompt,
        }

        compaction_query = Query(
            structured_prompt=templates.render("character/compact_sketch.system"),
            query_text=json.dumps(compaction_input),
            repetitions=2,
        )

        compact_response = self.router.get_response(
            compaction_query,
            Capability.TEXT,
            self.config.sketch_compact_model_interface,
        )

        # Parse the JSON response to get both front and back prompts
        try:
            prompts_data = output_formatting.safe_json_decode(compact_response["text"])
            front_prompt = prompts_data["front_prompt"]
            back_prompt = prompts_data["back_prompt"]
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse compacted prompts: {e}")
            # Fallback to the old single prompt approach
            front_prompt = compact_response["text"]
            back_prompt = compact_response["text"]

        # Ensure both prompts have view_angle placeholder
        for prompt_name, prompt in [("front", front_prompt), ("back", back_prompt)]:
            if "{view_angle}" not in prompt:
                if "view_angle" in prompt:
                    if prompt_name == "front":
                        front_prompt = front_prompt.replace(
                            "view_angle", "{view_angle}"
                        )
                    else:
                        back_prompt = back_prompt.replace("view_angle", "{view_angle}")
                else:
                    logger.warning(
                        f"Compacted {prompt_name} prompt missing {{view_angle}} placeholder. "
                        "Appending at the end."
                    )
                    if prompt_name == "front":
                        front_prompt += ", generate image from {view_angle}"
                    else:
                        back_prompt += ", generate image from {view_angle}"

        logger.info(f"Compacted front prompt: {front_prompt}")
        logger.info(f"Compacted back prompt: {back_prompt}")

        # Define which view angles should use the back prompt
        back_view_angles = {
            "back",
            "back_left_quarter",
            "back_right_quarter",
            "back_left_high",
            "back_right_high",
        }

        reference_image: str | None = None

        # Generate sketches for each configured view
        if (views_to_generate := self.config.character_views) is None:
            raise ValueError("Character views not configured properly.")

        for idx, view_angle in enumerate(views_to_generate):
            logger.info(f"Generating character sketch for view: {view_angle}")

            # Select appropriate prompt based on view angle
            if view_angle in back_view_angles:
                selected_prompt = back_prompt
                prompt_type = "back"
            else:
                selected_prompt = front_prompt
                prompt_type = "front"

            # Create the image generation query
            image_query = ImageGenQuery(
                query_text=selected_prompt.format(view_angle=view_angle),
                image_resolution=(1024, 1024),
                images=reference_image,
                repetitions=2,
            )

            # Generate the image using the model router
            response = self.router.get_response(
                image_query, Capability.IMAGE_GEN, self.config.sketch_model_interface
            )

            sketches[view_angle] = {
                "image": response["images"][0],
                "prompt": selected_prompt,
                "prompt_type": prompt_type,
                "view_angle": view_angle,
            }

            if idx == 0:
                if view_angle != "front":
                    raise ValueError(
                        "First view must be 'front' to provide a reference image for consistency."
                    )
                reference_image = sketches[view_angle]["image"]

        # Return the base64 encoded images with their view metadata
        return sketches

    def compile_video(
        self,
        character_element: character.Character,
        shots: List[Dict[str, str]],
        on_shot_complete: Callable[[str, str], None] | None = None,
    ) -> Dict[str, Any]:
        """Compile a character video from shot descriptions.

        The character's reference sketch is used as the seed image (first frame)
        for shot 1.  Subsequent shots use the last frame of the previous video
        as seed_image for continuity.

        Args:
            character_element: Character object with config and sketches
            shots: List of dicts with 'id' and 'description' keys
            on_shot_complete: Optional callback(shot_id, video_url) called after
                each shot is generated and uploaded, for incremental persistence.

        Returns:
            Dict with 'shots' key containing list of dicts with 'id' and 'video_url'
        """
        character_name = character_element.config.name
        visual_description = (
            character_element.config.compact_visual_description or character_name
        )

        logger.info(
            f"compile_video called for '{character_name}' with {len(shots)} shots"
        )

        if not character_element.sketches:
            raise ValueError(
                f"Character '{character_name}' has no sketches for video"
            )

        # Shot 1 seed = character sketch; shot N seed = last frame of N-1
        current_seed: Image.Image = character_element.sketches[0]
        compiled_shots = []

        for shot in shots:
            shot_id = shot["id"]
            description = shot.get("description", "").strip()

            if not description:
                compiled_shots.append({"id": shot_id, "video_url": None})
                continue

            try:
                prompt = f"{visual_description}. {description}"

                video_query = VideoGenQuery(
                    query_text=prompt,
                    seed_image=current_seed,
                    duration=5.0,
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

                # Upload to Firebase Storage
                storage_path = (
                    f"character_videos/{character_name}/{uuid.uuid4().hex}.mp4"
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

                # Extract last frame for next shot's seed
                current_seed = extract_last_frame(video_bytes)

            except Exception as e:
                logger.error(f"  Shot {shot_id} failed: {e}")
                compiled_shots.append({"id": shot_id, "video_url": None})

        return {"shots": compiled_shots}
