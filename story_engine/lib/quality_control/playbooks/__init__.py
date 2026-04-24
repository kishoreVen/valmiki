"""Control playbooks for quality control pipeline."""

from typing import Dict, Type

from story_engine.lib.quality_control.playbook import Playbook
from story_engine.lib.quality_control.playbooks.global_solve import GlobalSolvePlaybook
from story_engine.lib.quality_control.playbooks.swarm_solve import SwarmSolvePlaybook
from story_engine.lib.quality_control.playbooks.multi_stage_solve import (
    MultiStageSolvePlaybook,
)
from story_engine.lib.quality_control.playbooks.batched_vision_solve import (
    BatchedVisionSolvePlaybook,
)

PLAYBOOK_REGISTRY: Dict[str, Type[Playbook]] = {
    "GlobalSolve": GlobalSolvePlaybook,
    "SwarmSolve": SwarmSolvePlaybook,
    "MultiStageSolve": MultiStageSolvePlaybook,
    "BatchedVisionSolve": BatchedVisionSolvePlaybook,
}
