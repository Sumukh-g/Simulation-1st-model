"""Stopping rules for optimization."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class StopReason(str, Enum):
    """Reason for stopping optimization."""

    NONE = "none"
    PLATEAU = "plateau"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONFIDENCE_MET = "confidence_met"
    MAX_ITERATIONS = "max_iterations"
    MAX_EVALUATIONS = "max_evaluations"
    CONVERGENCE = "convergence"
    USER_REQUESTED = "user_requested"


@dataclass
class StoppingConfig:
    """Configuration for stopping rules."""

    # Plateau detection
    plateau_window: int = 10  # Number of iterations to check
    plateau_threshold: float = 0.001  # Min improvement to not be plateau

    # Budget
    max_budget: float = float("inf")
    max_iterations: int = 1000
    max_evaluations: int = 10000
    max_wall_time_seconds: float = float("inf")

    # Convergence
    confidence_threshold: float = 0.95
    convergence_tolerance: float = 1e-6

    # Early stopping
    min_iterations: int = 10  # Don't stop before this


@dataclass
class StoppingState:
    """State for tracking stopping conditions."""

    iteration: int = 0
    evaluations: int = 0
    budget_spent: float = 0.0
    wall_time_seconds: float = 0.0
    best_scores: List[float] = field(default_factory=list)
    confidence_scores: List[float] = field(default_factory=list)
    stop_reason: StopReason = StopReason.NONE
    should_stop: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "evaluations": self.evaluations,
            "budget_spent": self.budget_spent,
            "wall_time_seconds": self.wall_time_seconds,
            "best_scores_count": len(self.best_scores),
            "stop_reason": self.stop_reason.value,
            "should_stop": self.should_stop,
        }


class StoppingRules:
    """Evaluates stopping conditions for optimization."""

    def __init__(self, config: StoppingConfig | None = None):
        self.config = config or StoppingConfig()
        self.state = StoppingState()

    def reset(self) -> None:
        """Reset stopping state."""
        self.state = StoppingState()

    def update(
        self,
        best_score: float | None = None,
        confidence: float | None = None,
        evaluations_this_step: int = 0,
        budget_spent_this_step: float = 0.0,
        wall_time_elapsed: float = 0.0,
    ) -> None:
        """Update state after an iteration."""
        self.state.iteration += 1
        self.state.evaluations += evaluations_this_step
        self.state.budget_spent += budget_spent_this_step
        self.state.wall_time_seconds = wall_time_elapsed

        if best_score is not None:
            self.state.best_scores.append(best_score)

        if confidence is not None:
            self.state.confidence_scores.append(confidence)

    def check(self) -> tuple[bool, StopReason]:
        """Check if optimization should stop."""
        # Don't stop before minimum iterations
        if self.state.iteration < self.config.min_iterations:
            return False, StopReason.NONE

        # Budget exhausted
        if self.state.budget_spent >= self.config.max_budget:
            self.state.should_stop = True
            self.state.stop_reason = StopReason.BUDGET_EXHAUSTED
            return True, StopReason.BUDGET_EXHAUSTED

        # Max iterations
        if self.state.iteration >= self.config.max_iterations:
            self.state.should_stop = True
            self.state.stop_reason = StopReason.MAX_ITERATIONS
            return True, StopReason.MAX_ITERATIONS

        # Max evaluations
        if self.state.evaluations >= self.config.max_evaluations:
            self.state.should_stop = True
            self.state.stop_reason = StopReason.MAX_EVALUATIONS
            return True, StopReason.MAX_EVALUATIONS

        # Wall time
        if self.state.wall_time_seconds >= self.config.max_wall_time_seconds:
            self.state.should_stop = True
            self.state.stop_reason = StopReason.BUDGET_EXHAUSTED
            return True, StopReason.BUDGET_EXHAUSTED

        # Confidence threshold met
        if self.state.confidence_scores:
            latest_confidence = self.state.confidence_scores[-1]
            if latest_confidence >= self.config.confidence_threshold:
                self.state.should_stop = True
                self.state.stop_reason = StopReason.CONFIDENCE_MET
                return True, StopReason.CONFIDENCE_MET

        # Plateau detection
        if len(self.state.best_scores) >= self.config.plateau_window:
            window = self.state.best_scores[-self.config.plateau_window :]
            improvement = max(window) - min(window)
            if improvement < self.config.plateau_threshold:
                self.state.should_stop = True
                self.state.stop_reason = StopReason.PLATEAU
                return True, StopReason.PLATEAU

        # Convergence (best score not changing)
        if len(self.state.best_scores) >= 3:
            recent = self.state.best_scores[-3:]
            if all(
                abs(recent[i] - recent[i + 1]) < self.config.convergence_tolerance
                for i in range(len(recent) - 1)
            ):
                self.state.should_stop = True
                self.state.stop_reason = StopReason.CONVERGENCE
                return True, StopReason.CONVERGENCE

        return False, StopReason.NONE

    def explain(self) -> str:
        """Explain why optimization stopped or continues."""
        if not self.state.should_stop:
            return (
                f"Optimization continues. Iteration {self.state.iteration}, "
                f"{self.state.evaluations} evaluations, "
                f"budget {self.state.budget_spent:.1f}/{self.config.max_budget:.1f}"
            )

        reason = self.state.stop_reason
        if reason == StopReason.PLATEAU:
            return (
                f"Stopped due to plateau: no improvement > {self.config.plateau_threshold} "
                f"in last {self.config.plateau_window} iterations"
            )
        elif reason == StopReason.BUDGET_EXHAUSTED:
            return f"Stopped due to budget exhaustion: {self.state.budget_spent:.1f} spent"
        elif reason == StopReason.CONFIDENCE_MET:
            return (
                f"Stopped because confidence threshold met: "
                f"{self.state.confidence_scores[-1]:.3f} >= {self.config.confidence_threshold}"
            )
        elif reason == StopReason.MAX_ITERATIONS:
            return f"Stopped at max iterations: {self.config.max_iterations}"
        elif reason == StopReason.MAX_EVALUATIONS:
            return f"Stopped at max evaluations: {self.config.max_evaluations}"
        elif reason == StopReason.CONVERGENCE:
            return "Stopped due to convergence: best score stabilized"
        else:
            return f"Stopped: {reason.value}"
