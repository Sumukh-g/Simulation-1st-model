"""Multi-Fidelity Bandit for GSIP."""
import numpy as np
from typing import Any, Dict, List, Optional
from enum import Enum


class FidelityLevel(str, Enum):
    CHEAP = "cheap"
    MID = "mid"
    HIGH = "high"


class MultiFidelityBandit:
    """
    Multi-Armed Bandit for fidelity allocation.
    
    Uses Thompson Sampling to balance exploration/exploitation
    when choosing which fidelity level to use for simulations.
    
    Features:
    - Thompson Sampling for arm selection
    - Cost-aware allocation
    - Correlation modeling between fidelities
    - Budget governance
    """
    
    def __init__(
        self,
        fidelity_costs: Optional[Dict[str, float]] = None,
        budget: float = 1000.0,
        correlation_threshold: float = 0.8,
        random_state: Optional[int] = None,
    ):
        """
        Initialize multi-fidelity bandit.
        
        Args:
            fidelity_costs: Cost per simulation at each fidelity
            budget: Total budget (in cost units)
            correlation_threshold: Min correlation to trust cheap results
            random_state: Random seed
        """
        self.fidelity_costs = fidelity_costs or {
            FidelityLevel.CHEAP: 1.0,
            FidelityLevel.MID: 5.0,
            FidelityLevel.HIGH: 25.0,
        }
        self.budget = budget
        self.remaining_budget = budget
        self.correlation_threshold = correlation_threshold
        self.rng = np.random.RandomState(random_state)
        
        # Beta distribution parameters for each arm
        # (successes, failures) where success = good correlation with truth
        self.alpha = {f: 1.0 for f in FidelityLevel}
        self.beta = {f: 1.0 for f in FidelityLevel}
        
        # Statistics
        self.pulls = {f: 0 for f in FidelityLevel}
        self.total_reward = {f: 0.0 for f in FidelityLevel}
        
        # Correlation tracking (cheap vs high, mid vs high)
        self.correlation_data: List[Dict[str, Any]] = []
    
    def select_fidelity(
        self,
        remaining_evals: int,
        force_high: bool = False,
    ) -> FidelityLevel:
        """
        Select fidelity level for next evaluation.
        
        Args:
            remaining_evals: Number of evaluations remaining
            force_high: Force high fidelity (e.g., for final validation)
        
        Returns:
            Selected fidelity level
        """
        if force_high or remaining_evals <= 5:
            # Final evaluations should use high fidelity
            return FidelityLevel.HIGH
        
        # Check budget constraints
        available = []
        for fidelity in FidelityLevel:
            if self.fidelity_costs[fidelity] <= self.remaining_budget:
                available.append(fidelity)
        
        if not available:
            return FidelityLevel.CHEAP  # Fallback
        
        if FidelityLevel.HIGH not in available:
            # If we can't afford high, use what we can
            return max(available, key=lambda f: self.fidelity_costs[f])
        
        # Thompson Sampling: sample from Beta distributions
        samples = {}
        for fidelity in available:
            # Sample expected "quality" of this fidelity
            sample = self.rng.beta(self.alpha[fidelity], self.beta[fidelity])
            
            # Adjust for cost efficiency
            cost = self.fidelity_costs[fidelity]
            samples[fidelity] = sample / np.sqrt(cost)  # Cost-adjusted
        
        # Select best sample
        return max(samples.keys(), key=lambda f: samples[f])
    
    def update(
        self,
        fidelity: FidelityLevel,
        score: float,
        high_fidelity_score: Optional[float] = None,
    ) -> None:
        """
        Update bandit with observation.
        
        Args:
            fidelity: Fidelity level used
            score: Score achieved
            high_fidelity_score: If available, true high-fidelity score
        """
        # Update counts
        self.pulls[fidelity] += 1
        self.total_reward[fidelity] += score
        
        # Update budget
        self.remaining_budget -= self.fidelity_costs[fidelity]
        
        # Update correlation if we have ground truth
        if high_fidelity_score is not None and fidelity != FidelityLevel.HIGH:
            # Compute reward based on correlation
            error = abs(score - high_fidelity_score)
            max_score = max(abs(score), abs(high_fidelity_score), 1e-6)
            relative_error = error / max_score
            
            # Reward: 1 if error is small, 0 if large
            reward = 1.0 if relative_error < (1 - self.correlation_threshold) else 0.0
            
            # Update Beta parameters
            self.alpha[fidelity] += reward
            self.beta[fidelity] += (1 - reward)
            
            # Store correlation data
            self.correlation_data.append({
                "fidelity": fidelity,
                "score": score,
                "high_score": high_fidelity_score,
                "error": relative_error,
            })
    
    def get_allocation_strategy(
        self,
        n_evaluations: int,
    ) -> Dict[FidelityLevel, int]:
        """
        Get recommended allocation of evaluations across fidelities.
        
        Args:
            n_evaluations: Total number of evaluations
        
        Returns:
            Recommended count for each fidelity level
        """
        # Simple strategy: most cheap, some mid, few high
        allocation = {
            FidelityLevel.CHEAP: int(n_evaluations * 0.6),
            FidelityLevel.MID: int(n_evaluations * 0.3),
            FidelityLevel.HIGH: int(n_evaluations * 0.1),
        }
        
        # Adjust for budget
        total_cost = sum(
            allocation[f] * self.fidelity_costs[f]
            for f in FidelityLevel
        )
        
        if total_cost > self.remaining_budget:
            # Scale down
            scale = self.remaining_budget / total_cost
            allocation = {
                f: max(1, int(c * scale))
                for f, c in allocation.items()
            }
        
        return allocation
    
    def should_promote(
        self,
        fidelity: FidelityLevel,
        score: float,
        threshold_percentile: float = 0.9,
    ) -> bool:
        """
        Decide if a cheap/mid result should be validated at higher fidelity.
        
        Args:
            fidelity: Current fidelity
            score: Current score
            threshold_percentile: Percentile threshold for promotion
        
        Returns:
            Whether to promote to higher fidelity
        """
        if fidelity == FidelityLevel.HIGH:
            return False
        
        # Get historical scores at this fidelity
        relevant = [
            d["score"] for d in self.correlation_data
            if d["fidelity"] == fidelity
        ]
        
        if len(relevant) < 5:
            # Not enough data, promote top results
            return True
        
        threshold = np.percentile(relevant, threshold_percentile * 100)
        return score >= threshold
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get bandit statistics."""
        return {
            "pulls": dict(self.pulls),
            "total_reward": dict(self.total_reward),
            "avg_reward": {
                f: self.total_reward[f] / max(self.pulls[f], 1)
                for f in FidelityLevel
            },
            "remaining_budget": self.remaining_budget,
            "alpha": dict(self.alpha),
            "beta": dict(self.beta),
            "correlation_samples": len(self.correlation_data),
        }
