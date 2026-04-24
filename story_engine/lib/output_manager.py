
import logging

import hydra.core.hydra_config

logger = logging.getLogger(__name__)


class OutputManager:
    """Singleton to manage Hydra output directory access."""

    _instance: "OutputManager | None" = None
    _output_dir: str | None = None

    @classmethod
    def instance(cls) -> "OutputManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def output_dir(self) -> str:
        if self._output_dir is None:
            self.output_dir = (
                hydra.core.hydra_config.HydraConfig.get().runtime.output_dir
            )

        assert self._output_dir is not None
        return self._output_dir

    @output_dir.setter
    def output_dir(self, value: str) -> None:
        self._output_dir = value

        logger.info(f"Output directory set to: {self._output_dir}")
