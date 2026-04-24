
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict

from story_engine.lib.model_router.model_interface import Capability


@dataclass
class PromptData:
    """
    A data class that holds the prompt data for various elements.
    """

    unique_identifier: str = ""
    capability_prompt: Dict[Capability, Any] = field(default_factory=dict)


class IPromptGeneratable(ABC):
    """
    An abstract base class that defines an interface for prompt generation.
    Child classes should override the generate_prompt method to implement
    their specific prompt generation logic.
    """

    def __init__(self, identifier: str) -> None:
        self.prompt_data: PromptData = PromptData(unique_identifier=identifier)
        self._build_prompt_data()

    @property
    def identifier(self) -> str:
        return self.prompt_data.unique_identifier

    @abstractmethod
    def _build_prompt_data(self) -> None:
        """
        Should populate all the capability prompts for the element.
        """
        pass
