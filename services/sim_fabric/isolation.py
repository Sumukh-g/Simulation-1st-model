"""Isolation strategies for domain pack execution."""
from __future__ import annotations

import logging
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

logger = logging.getLogger(__name__)


class IsolationMode(str, Enum):
    """Isolation modes for domain pack execution."""

    NONE = "none"  # No isolation, run in current process
    SUBPROCESS = "subprocess"  # Run in subprocess with fresh env
    CONTAINER = "container"  # Run in Docker container (stub)


@dataclass
class IsolationConfig:
    """Configuration for isolation."""

    mode: IsolationMode = IsolationMode.NONE
    timeout_seconds: int = 300
    memory_limit_mb: int = 4096
    cpu_limit: float = 2.0
    network_enabled: bool = False
    container_image: str | None = None
    env_vars: Dict[str, str] | None = None


class IsolationStrategy(ABC):
    """Base class for isolation strategies."""

    @abstractmethod
    def execute(
        self,
        pack_module: str,
        pack_version: str,
        state: Dict[str, Any],
        actions: Dict[str, Any],
        fidelity: str,
        seed: int,
        scenario_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        """Execute a simulation with isolation."""
        raise NotImplementedError


class NoIsolation(IsolationStrategy):
    """No isolation - runs in the current process."""

    def execute(
        self,
        pack_module: str,
        pack_version: str,
        state: Dict[str, Any],
        actions: Dict[str, Any],
        fidelity: str,
        seed: int,
        scenario_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        """Execute without isolation."""
        # Import and run directly
        from compute.domain_packs.sdk import DomainPackRegistry, Fidelity

        pack = DomainPackRegistry.create_instance(pack_module, pack_version)
        validated_state = pack.validate_state(state)
        validated_actions = pack.validate_actions(actions)

        feasibility = pack.feasibility(validated_state, validated_actions)
        if not feasibility.is_feasible:
            return {
                "status": "failed",
                "error": f"Infeasible: {feasibility.violations}",
                "scenario_id": scenario_id,
                "run_id": run_id,
            }

        fidelity_enum = Fidelity(fidelity)
        outcome = pack.simulate(
            state=validated_state,
            actions=validated_actions,
            fidelity=fidelity_enum,
            seed=seed,
            scenario_id=scenario_id,
            run_id=run_id,
        )

        return {
            "status": "completed",
            "outcome": outcome.model_dump(),
            "scenario_id": scenario_id,
            "run_id": run_id,
        }


class SubprocessIsolation(IsolationStrategy):
    """Run simulation in a subprocess with fresh environment."""

    def __init__(self, config: IsolationConfig):
        self.config = config

    def execute(
        self,
        pack_module: str,
        pack_version: str,
        state: Dict[str, Any],
        actions: Dict[str, Any],
        fidelity: str,
        seed: int,
        scenario_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        """Execute in subprocess."""
        import json

        script = f'''
import json
import sys
sys.path.insert(0, ".")

from compute.domain_packs.sdk import DomainPackRegistry, Fidelity

pack = DomainPackRegistry.create_instance("{pack_module}", "{pack_version}")
state = json.loads('{json.dumps(state)}')
actions = json.loads('{json.dumps(actions)}')

validated_state = pack.validate_state(state)
validated_actions = pack.validate_actions(actions)

feasibility = pack.feasibility(validated_state, validated_actions)
if not feasibility.is_feasible:
    result = {{"status": "failed", "error": str(feasibility.violations)}}
else:
    outcome = pack.simulate(
        state=validated_state,
        actions=validated_actions,
        fidelity=Fidelity("{fidelity}"),
        seed={seed},
        scenario_id="{scenario_id}",
        run_id="{run_id}",
    )
    result = {{"status": "completed", "outcome": outcome.model_dump()}}

result["scenario_id"] = "{scenario_id}"
result["run_id"] = "{run_id}"
print(json.dumps(result))
'''

        try:
            env = os.environ.copy()
            if self.config.env_vars:
                env.update(self.config.env_vars)

            result = subprocess.run(
                ["python", "-c", script],
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                env=env,
            )

            if result.returncode != 0:
                return {
                    "status": "failed",
                    "error": result.stderr,
                    "scenario_id": scenario_id,
                    "run_id": run_id,
                }

            return json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "error": "Simulation timed out",
                "scenario_id": scenario_id,
                "run_id": run_id,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "error": str(exc),
                "scenario_id": scenario_id,
                "run_id": run_id,
            }


class ContainerIsolation(IsolationStrategy):
    """Run simulation in a Docker container (stub implementation)."""

    def __init__(self, config: IsolationConfig):
        self.config = config

    def execute(
        self,
        pack_module: str,
        pack_version: str,
        state: Dict[str, Any],
        actions: Dict[str, Any],
        fidelity: str,
        seed: int,
        scenario_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        """Execute in Docker container (stub)."""

        # This is a stub - in production, this would:
        # 1. Build/pull container image for the domain pack
        # 2. Mount necessary volumes
        # 3. Run simulation inside container
        # 4. Collect results

        if not self.config.container_image:
            return {
                "status": "failed",
                "error": "Container image not specified",
                "scenario_id": scenario_id,
                "run_id": run_id,
            }

        logger.info(
            f"Container isolation stub: would run {pack_module}:{pack_version} "
            f"in {self.config.container_image}"
        )

        # Fall back to no isolation for now
        fallback = NoIsolation()
        return fallback.execute(
            pack_module,
            pack_version,
            state,
            actions,
            fidelity,
            seed,
            scenario_id,
            run_id,
        )


def get_isolation_strategy(config: IsolationConfig) -> IsolationStrategy:
    """Get the appropriate isolation strategy."""
    if config.mode == IsolationMode.NONE:
        return NoIsolation()
    elif config.mode == IsolationMode.SUBPROCESS:
        return SubprocessIsolation(config)
    elif config.mode == IsolationMode.CONTAINER:
        return ContainerIsolation(config)
    else:
        return NoIsolation()
