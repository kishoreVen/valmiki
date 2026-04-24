
"""
Base class for image generation model interfaces that support optional prompt compaction.

Some models (like diffusion models) benefit from having prompts compacted before generation,
while others (like OpenAI and Gemini) handle long prompts natively and don't need compaction.
"""

from abc import abstractmethod
from typing import Any, Dict, List

from story_engine.lib.model_router.model_interface import (
    ModelInterface,
    Query,
    ImageGenQuery,
    Capability,
)

import logging
from dataclasses import replace

logger = logging.getLogger(__name__)


class ImageGenerationModelInterface(ModelInterface):
    """
    Base class for image generation models that support optional prompt compaction.

    Models that need prompt compaction should extend this class and implement
    `_fetch_image_response`. The compaction logic is handled automatically in
    `fetch_response` if a compaction_prompt is provided in the query.

    Models that don't need compaction (like OpenAI and Gemini native interfaces)
    should extend ModelInterface directly and implement fetch_response.
    """

    def __init__(self, seed: int | None) -> None:
        super().__init__(seed)
        # Lazy import to avoid circular dependency
        self._router = None

    def _get_router(self):
        """Lazily initialize the ModelRouter for compaction queries."""
        if self._router is None:
            from story_engine.lib.model_router.router import ModelRouter

            self._router = ModelRouter()
        return self._router

    def _compact_prompt(self, query: ImageGenQuery) -> str:
        """
        Compact the query text using the compaction prompt and model.

        Args:
            query: The ImageGenQuery containing the text to compact and compaction settings

        Returns:
            The compacted prompt text ready for the diffusion model
        """
        # Create a text query for compaction
        compaction_query = Query(
            system_prompt=query.compaction_prompt,
            query_text=query.make_query(),
        )

        # Run compaction through the router
        router = self._get_router()
        response = router.get_response(
            compaction_query,
            Capability.TEXT,
            query.compaction_model,
        )

        compacted_text = response["text"]
        logger.debug(
            f"Compacted prompt from {len(original_text)} to {len(compacted_text)} chars"
        )

        return compacted_text

    def fetch_response(
        self, query: Query, capability: Capability | None = None
    ) -> Dict[str, Any]:
        """
        Fetch image generation response, optionally compacting the prompt first.

        If the query has a compaction_prompt set, the query_text will be compacted
        before being passed to _fetch_image_response. Otherwise, the query is passed
        through as-is.

        Args:
            query: The ImageGenQuery to process
            capability: The capability being requested (should be IMAGE_GEN)

        Returns:
            Dict containing the generated images
        """
        if not isinstance(query, ImageGenQuery):
            raise ValueError("Image generation requires ImageGenQuery")

        # Check if compaction is requested
        if query.compaction_prompt:
            # Compact the prompt
            compacted_text = self._compact_prompt(query)

            compacted_query = replace(
                query,
                query_text=compacted_text,
                system_prompt=None,
                # Clear compaction settings to prevent re-compaction
                compaction_prompt=None,
            )

            return self._fetch_image_response(compacted_query, capability)
        else:
            return self._fetch_image_response(query, capability)

    @abstractmethod
    def _fetch_image_response(
        self, query: ImageGenQuery, capability: Capability | None = None
    ) -> Dict[str, Any]:
        """
        Fetch the image generation response from the model.

        This method should be implemented by subclasses to perform the actual
        image generation. The query passed to this method may have already been
        compacted if compaction_prompt was set.

        Args:
            query: The ImageGenQuery (potentially with compacted text)
            capability: The capability being requested

        Returns:
            Dict containing the generated images under the "images" key
        """
        ...

    def supported_capabilities(self) -> List[Capability]:
        return [Capability.IMAGE_GEN]
