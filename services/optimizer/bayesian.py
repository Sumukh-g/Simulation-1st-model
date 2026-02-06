"""Bayesian Optimization for GSIP."""
import numpy as np
from typing import Any, Dict, List, Optional, Tuple
from scipy.stats import norm
from scipy.optimize import minimize
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, ConstantKernel


class BayesianOptimizer:
    """
    Bayesian Optimization using Gaussian Process surrogate.
    
    Features:
    - Gaussian Process regression for surrogate model
    - Expected Improvement acquisition function
    - Support for bounded continuous parameters
    - Batch proposal support
    """
    
    def __init__(
        self,
        bounds: Dict[str, Tuple[float, float]],
        maximize: bool = True,
        kernel: str = "matern",
        n_restarts: int = 10,
        random_state: Optional[int] = None,
    ):
        """
        Initialize Bayesian optimizer.
        
        Args:
            bounds: Parameter bounds {name: (lower, upper)}
            maximize: Whether to maximize (True) or minimize (False)
            kernel: Kernel type ('matern' or 'rbf')
            n_restarts: Number of restarts for optimization
            random_state: Random seed for reproducibility
        """
        self.bounds = bounds
        self.param_names = list(bounds.keys())
        self.n_params = len(self.param_names)
        self.maximize = maximize
        self.n_restarts = n_restarts
        self.random_state = random_state
        
        # Build bounds array
        self.bounds_array = np.array([bounds[name] for name in self.param_names])
        
        # Initialize GP
        if kernel == "matern":
            kern = ConstantKernel(1.0) * Matern(length_scale=1.0, nu=2.5)
        else:
            kern = ConstantKernel(1.0) * Matern(length_scale=1.0, nu=0.5)
        
        self.gp = GaussianProcessRegressor(
            kernel=kern,
            alpha=1e-6,
            normalize_y=True,
            n_restarts_optimizer=5,
            random_state=random_state,
        )
        
        # History
        self.X_observed: List[np.ndarray] = []
        self.y_observed: List[float] = []
        self.best_score: Optional[float] = None
        self.best_params: Optional[Dict[str, float]] = None
    
    def _params_to_array(self, params: Dict[str, float]) -> np.ndarray:
        """Convert params dict to numpy array."""
        return np.array([params[name] for name in self.param_names])
    
    def _array_to_params(self, x: np.ndarray) -> Dict[str, float]:
        """Convert numpy array to params dict."""
        return {name: float(x[i]) for i, name in enumerate(self.param_names)}
    
    def _expected_improvement(
        self,
        x: np.ndarray,
        xi: float = 0.01,
    ) -> float:
        """
        Compute Expected Improvement acquisition function.
        
        EI(x) = E[max(f(x) - f(x_best), 0)]
        """
        x = x.reshape(1, -1)
        
        mu, sigma = self.gp.predict(x, return_std=True)
        sigma = sigma.reshape(-1)
        
        if sigma[0] < 1e-10:
            return 0.0
        
        if self.maximize:
            improvement = mu[0] - self.best_score - xi
        else:
            improvement = self.best_score - mu[0] - xi
        
        z = improvement / sigma[0]
        ei = improvement * norm.cdf(z) + sigma[0] * norm.pdf(z)
        
        return ei
    
    def _neg_expected_improvement(self, x: np.ndarray) -> float:
        """Negative EI for minimization."""
        return -self._expected_improvement(x)
    
    def observe(self, params: Dict[str, float], score: float) -> None:
        """
        Record an observation.
        
        Args:
            params: Parameter values
            score: Observed score
        """
        x = self._params_to_array(params)
        self.X_observed.append(x)
        self.y_observed.append(score)
        
        # Update best
        if self.maximize:
            if self.best_score is None or score > self.best_score:
                self.best_score = score
                self.best_params = params.copy()
        else:
            if self.best_score is None or score < self.best_score:
                self.best_score = score
                self.best_params = params.copy()
    
    def fit(self) -> None:
        """Fit the GP model to observed data."""
        if len(self.X_observed) < 2:
            return
        
        X = np.array(self.X_observed)
        y = np.array(self.y_observed)
        
        self.gp.fit(X, y)
    
    def propose(self, n_candidates: int = 1) -> List[Dict[str, float]]:
        """
        Propose next parameters to evaluate.
        
        Args:
            n_candidates: Number of candidates to propose
        
        Returns:
            List of parameter dictionaries
        """
        rng = np.random.RandomState(self.random_state)
        
        # If not enough data, return random samples
        if len(self.X_observed) < 3:
            candidates = []
            for _ in range(n_candidates):
                params = {}
                for name in self.param_names:
                    low, high = self.bounds[name]
                    params[name] = rng.uniform(low, high)
                candidates.append(params)
            return candidates
        
        # Fit GP
        self.fit()
        
        candidates = []
        for _ in range(n_candidates):
            # Optimize acquisition function with multiple restarts
            best_x = None
            best_ei = -np.inf
            
            for _ in range(self.n_restarts):
                # Random starting point
                x0 = rng.uniform(
                    self.bounds_array[:, 0],
                    self.bounds_array[:, 1],
                )
                
                # Optimize
                result = minimize(
                    self._neg_expected_improvement,
                    x0,
                    method="L-BFGS-B",
                    bounds=self.bounds_array,
                )
                
                ei = -result.fun
                if ei > best_ei:
                    best_ei = ei
                    best_x = result.x
            
            if best_x is not None:
                candidates.append(self._array_to_params(best_x))
            else:
                # Fallback to random
                params = {}
                for name in self.param_names:
                    low, high = self.bounds[name]
                    params[name] = rng.uniform(low, high)
                candidates.append(params)
        
        return candidates
    
    def get_state(self) -> Dict[str, Any]:
        """Get optimizer state for serialization."""
        return {
            "bounds": self.bounds,
            "maximize": self.maximize,
            "X_observed": [x.tolist() for x in self.X_observed],
            "y_observed": self.y_observed,
            "best_score": self.best_score,
            "best_params": self.best_params,
        }
    
    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "BayesianOptimizer":
        """Restore optimizer from state."""
        opt = cls(
            bounds=state["bounds"],
            maximize=state["maximize"],
        )
        opt.X_observed = [np.array(x) for x in state["X_observed"]]
        opt.y_observed = state["y_observed"]
        opt.best_score = state["best_score"]
        opt.best_params = state["best_params"]
        return opt
