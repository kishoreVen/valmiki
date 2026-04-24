
from dataclasses import dataclass, field

from typing import List

from story_engine.lib.model_router.utils import base64_to_image
from story_engine.interfaces import prompt_generatable

from story_engine.lib.model_router.model_interface import Capability

from story_engine.lib import prompt_formatting

from PIL import Image

import logging

logger = logging.getLogger(__name__)


@dataclass
class CharacterConfig:
    identifier: str

    visual_description: str | None = None

    voice_description: str | None = None

    compact_visual_description: str | None = None

    backstory: str = ""

    name: str = ""

    gender: str = ""

    age: int | None = None

    goals: List[str] = field(default_factory=list)

    weaknesses: List[str] = field(default_factory=list)


INPUT_FORMAT: str = """{
    "name": string,          // Name of the character (use this exact name when referencing the character)
    "gender": string,        // Gender of the character
    "age": int,             // Age of the character
    "backstory": string,     // Backstory of the character
    "goals": string[],       // List of goals the character has that should be used to create plot points where they are trying to achieve something or helping others. Ideally between 3 to 5.
    "weaknesses": string[],  // List of weaknesses the character has that should be used to create plot points where they are vulnerable and need help. Ideally between 2 to 3.
}"""

_PROMPT: str = """{{
    name: {name},
    gender: {gender},
    age: {age},
    backstory: {backstory},
    goals: {goals},
    weaknesses: {weaknesses},
}}"""

_VISUAL_PROMPT: str = (
    """Not Photorealistic. Children Appropriate. {visual_description}"""
)

_VOICE_PROMPT: str = (
    """For voice generation capabilities use a {gender} voice appropriate for a person who is {age} years old. {voice_description}"""
)


class Character(prompt_generatable.IPromptGeneratable):
    def __init__(self, config: CharacterConfig) -> None:
        self.config = config

        super().__init__(config.identifier)

        self.sketches: List[Image.Image] = []

    def _build_prompt_data(self) -> None:
        if self.config.age is None or self.config.gender is None:
            raise ValueError(
                "Character must have age and gender at the very least. "
                "Maybe use CharacterDesigner to flesh out the character?"
            )

        self.prompt_data.capability_prompt[Capability.TEXT] = _PROMPT.format(
            name=self.config.name,
            age=self.config.age,
            gender=self.config.gender,
            backstory=self.config.backstory,
            goals=prompt_formatting.format_list(self.config.goals),
            weaknesses=prompt_formatting.format_list(self.config.weaknesses),
        )

        # Add image capability data if available
        if (description := self.config.visual_description) is not None:
            self.prompt_data.capability_prompt[Capability.IMAGE_GEN] = (
                _VISUAL_PROMPT.format(
                    visual_description=description,
                )
            )

        # Add audio capability data if available
        if (description := self.config.voice_description) is not None:
            self.prompt_data.capability_prompt[Capability.AUDIO_GEN] = (
                _VOICE_PROMPT.format(
                    age=self.config.age,
                    gender=self.config.gender,
                    voice_description=description,
                )
            )

        # Convert to JSON string
        logger.debug(f"Character Prompt for {self.config.name}: {self.prompt_data}")

    def append_sketch(self, character_sketch: Image.Image | str) -> None:
        if isinstance(character_sketch, str):
            character_sketch = base64_to_image(character_sketch)

        self.sketches.append(character_sketch)
