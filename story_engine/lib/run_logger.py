"""
Run-level prompt/response logger for pipeline inspection.

Captures every prompt sent to a model and the response received,
organized by pipeline run and stage. Data is saved to output/{run_id}/
as JSON for the story_viewer's PromptInspector.

Usage:
    from story_engine.lib.run_logger import RunLogger, get_run_logger

    # Start a new run
    run_logger = RunLogger(run_id="run_001")

    # Log a prompt/response pair
    run_logger.log(
        stage="concept",
        step="create",
        template_name="concept/create.system",
        system_prompt=structured_prompt.to_flat_prompt(),
        user_prompt=user_text,
        response_text=response["text"],
        model_interface="anthropic_sonnet4",
        usage=response.get("usage"),
        cost=response.get("cost"),
    )

    # Save all logs for this run
    run_logger.save()
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")

# Thread-local storage for the active run logger
_local = threading.local()


@dataclass
class PromptLog:
    """A single prompt/response exchange."""
    timestamp: float
    stage: str
    step: str
    template_name: str
    system_prompt: str
    user_prompt: str
    response_text: str
    model_interface: str
    usage: Optional[Dict[str, int]] = None
    cost: Optional[float] = None
    iteration: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageLog:
    """All exchanges for a single pipeline stage."""
    stage: str
    started_at: float = 0.0
    completed_at: float = 0.0
    entries: List[PromptLog] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed

    @property
    def total_cost(self) -> float:
        return sum(e.cost or 0.0 for e in self.entries)

    @property
    def total_input_tokens(self) -> int:
        return sum((e.usage or {}).get("input_tokens", 0) for e in self.entries)

    @property
    def total_output_tokens(self) -> int:
        return sum((e.usage or {}).get("output_tokens", 0) for e in self.entries)


class RunLogger:
    """Captures prompt/response pairs for a full pipeline run."""

    def __init__(self, run_id: str, output_dir: Optional[Path] = None) -> None:
        self.run_id = run_id
        self.output_dir = (output_dir or OUTPUT_DIR) / run_id
        self.stages: Dict[str, StageLog] = {}
        self.started_at = time.time()
        self.status = "running"
        self._lock = threading.Lock()

    def _get_stage(self, stage: str) -> StageLog:
        if stage not in self.stages:
            self.stages[stage] = StageLog(stage=stage, started_at=time.time(), status="running")
        return self.stages[stage]

    def log(
        self,
        stage: str,
        step: str,
        template_name: str,
        system_prompt: str,
        user_prompt: str,
        response_text: str,
        model_interface: str,
        usage: Optional[Dict[str, int]] = None,
        cost: Optional[float] = None,
        iteration: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a prompt/response exchange."""
        entry = PromptLog(
            timestamp=time.time(),
            stage=stage,
            step=step,
            template_name=template_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response_text,
            model_interface=model_interface,
            usage=usage,
            cost=cost,
            iteration=iteration,
            metadata=metadata or {},
        )
        with self._lock:
            self._get_stage(stage).entries.append(entry)

    def mark_stage_complete(self, stage: str) -> None:
        with self._lock:
            if stage in self.stages:
                self.stages[stage].completed_at = time.time()
                self.stages[stage].status = "completed"

    def mark_stage_failed(self, stage: str, error: str = "") -> None:
        with self._lock:
            if stage in self.stages:
                self.stages[stage].completed_at = time.time()
                self.stages[stage].status = "failed"

    def save(self) -> Path:
        """Save all logs to output/{run_id}/prompts.json."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / "prompts.json"

        data = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "status": self.status,
            "stages": {},
        }

        for name, stage in self.stages.items():
            data["stages"][name] = {
                "stage": stage.stage,
                "status": stage.status,
                "started_at": stage.started_at,
                "completed_at": stage.completed_at,
                "total_cost": stage.total_cost,
                "total_input_tokens": stage.total_input_tokens,
                "total_output_tokens": stage.total_output_tokens,
                "entries": [asdict(e) for e in stage.entries],
            }

        out_path.write_text(json.dumps(data, indent=2))
        logger.info(f"Run logs saved to {out_path}")
        return out_path

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the run for the API."""
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "status": self.status,
            "stages": {
                name: {
                    "status": stage.status,
                    "entries_count": len(stage.entries),
                    "total_cost": stage.total_cost,
                    "total_input_tokens": stage.total_input_tokens,
                    "total_output_tokens": stage.total_output_tokens,
                }
                for name, stage in self.stages.items()
            },
        }


def set_run_logger(run_logger: RunLogger) -> None:
    """Set the active run logger for the current thread."""
    _local.run_logger = run_logger


def get_run_logger() -> Optional[RunLogger]:
    """Get the active run logger for the current thread."""
    return getattr(_local, "run_logger", None)


def clear_run_logger() -> None:
    """Clear the active run logger."""
    _local.run_logger = None
