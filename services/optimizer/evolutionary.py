"""Evolutionary Optimization for GSIP."""
import numpy as np
from typing import Any, Dict, List, Optional, Tuple


class EvolutionaryOptimizer:
    """
    Multi-Objective Evolutionary Optimization using NSGA-II.
    
    Features:
    - Non-dominated sorting
    - Crowding distance for diversity
    - Tournament selection
    - SBX crossover and polynomial mutation
    - Pareto frontier tracking
    """
    
    def __init__(
        self,
        bounds: Dict[str, Tuple[float, float]],
        objectives: List[str],
        maximize: Optional[List[bool]] = None,
        population_size: int = 50,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.9,
        random_state: Optional[int] = None,
    ):
        """
        Initialize evolutionary optimizer.
        
        Args:
            bounds: Parameter bounds {name: (lower, upper)}
            objectives: List of objective names
            maximize: Whether to maximize each objective (default: all True)
            population_size: Population size
            mutation_rate: Probability of mutation
            crossover_rate: Probability of crossover
            random_state: Random seed
        """
        self.bounds = bounds
        self.param_names = list(bounds.keys())
        self.n_params = len(self.param_names)
        self.objectives = objectives
        self.n_objectives = len(objectives)
        self.maximize = maximize or [True] * self.n_objectives
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.rng = np.random.RandomState(random_state)
        
        # Bounds array
        self.bounds_array = np.array([bounds[name] for name in self.param_names])
        
        # Population: list of (params, objective_values)
        self.population: List[Tuple[Dict[str, float], Optional[Dict[str, float]]]] = []
        self.generation = 0
        
        # Pareto frontier
        self.pareto_frontier: List[Tuple[Dict[str, float], Dict[str, float]]] = []
    
    def _random_individual(self) -> Dict[str, float]:
        """Generate a random individual."""
        return {
            name: self.rng.uniform(low, high)
            for name, (low, high) in self.bounds.items()
        }
    
    def _dominates(
        self,
        obj1: Dict[str, float],
        obj2: Dict[str, float],
    ) -> bool:
        """Check if obj1 dominates obj2."""
        dominated = False
        for i, name in enumerate(self.objectives):
            v1 = obj1.get(name, 0)
            v2 = obj2.get(name, 0)
            
            if self.maximize[i]:
                if v1 < v2:
                    return False
                if v1 > v2:
                    dominated = True
            else:
                if v1 > v2:
                    return False
                if v1 < v2:
                    dominated = True
        
        return dominated
    
    def _non_dominated_sort(
        self,
        population: List[Tuple[Dict[str, float], Dict[str, float]]],
    ) -> List[List[int]]:
        """Perform non-dominated sorting."""
        n = len(population)
        if n == 0:
            return []
        
        # Domination counts and dominated sets
        domination_count = [0] * n
        dominated_by = [[] for _ in range(n)]
        
        for i in range(n):
            for j in range(i + 1, n):
                if population[i][1] is None or population[j][1] is None:
                    continue
                
                if self._dominates(population[i][1], population[j][1]):
                    dominated_by[i].append(j)
                    domination_count[j] += 1
                elif self._dominates(population[j][1], population[i][1]):
                    dominated_by[j].append(i)
                    domination_count[i] += 1
        
        # Build fronts
        fronts = []
        current_front = [i for i in range(n) if domination_count[i] == 0]
        
        while current_front:
            fronts.append(current_front)
            next_front = []
            for i in current_front:
                for j in dominated_by[i]:
                    domination_count[j] -= 1
                    if domination_count[j] == 0:
                        next_front.append(j)
            current_front = next_front
        
        return fronts
    
    def _crowding_distance(
        self,
        front: List[int],
        population: List[Tuple[Dict[str, float], Dict[str, float]]],
    ) -> List[float]:
        """Compute crowding distance for a front."""
        n = len(front)
        if n <= 2:
            return [float('inf')] * n
        
        distances = [0.0] * n
        
        for obj_name in self.objectives:
            # Sort by this objective
            sorted_indices = sorted(
                range(n),
                key=lambda i: population[front[i]][1].get(obj_name, 0) if population[front[i]][1] else 0,
            )
            
            # Boundary points get infinite distance
            distances[sorted_indices[0]] = float('inf')
            distances[sorted_indices[-1]] = float('inf')
            
            # Compute objective range
            values = [population[front[i]][1].get(obj_name, 0) if population[front[i]][1] else 0 for i in front]
            obj_range = max(values) - min(values)
            
            if obj_range > 0:
                for i in range(1, n - 1):
                    prev_val = population[front[sorted_indices[i-1]]][1].get(obj_name, 0)
                    next_val = population[front[sorted_indices[i+1]]][1].get(obj_name, 0)
                    distances[sorted_indices[i]] += (next_val - prev_val) / obj_range
        
        return distances
    
    def _sbx_crossover(
        self,
        parent1: Dict[str, float],
        parent2: Dict[str, float],
        eta: float = 20.0,
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Simulated Binary Crossover."""
        child1, child2 = {}, {}
        
        for name in self.param_names:
            low, high = self.bounds[name]
            p1, p2 = parent1[name], parent2[name]
            
            if self.rng.random() < 0.5:
                if abs(p1 - p2) > 1e-10:
                    if p1 < p2:
                        y1, y2 = p1, p2
                    else:
                        y1, y2 = p2, p1
                    
                    beta = 1.0 + (2.0 * (y1 - low) / (y2 - y1))
                    alpha = 2.0 - beta ** (-(eta + 1))
                    rand = self.rng.random()
                    
                    if rand <= 1.0 / alpha:
                        betaq = (rand * alpha) ** (1.0 / (eta + 1))
                    else:
                        betaq = (1.0 / (2.0 - rand * alpha)) ** (1.0 / (eta + 1))
                    
                    c1 = 0.5 * ((y1 + y2) - betaq * (y2 - y1))
                    c2 = 0.5 * ((y1 + y2) + betaq * (y2 - y1))
                    
                    child1[name] = max(low, min(high, c1))
                    child2[name] = max(low, min(high, c2))
                else:
                    child1[name], child2[name] = p1, p2
            else:
                child1[name], child2[name] = p1, p2
        
        return child1, child2
    
    def _polynomial_mutation(
        self,
        individual: Dict[str, float],
        eta: float = 20.0,
    ) -> Dict[str, float]:
        """Polynomial mutation."""
        mutated = {}
        
        for name in self.param_names:
            low, high = self.bounds[name]
            value = individual[name]
            
            if self.rng.random() < self.mutation_rate:
                delta1 = (value - low) / (high - low)
                delta2 = (high - value) / (high - low)
                rand = self.rng.random()
                
                if rand < 0.5:
                    xy = 1.0 - delta1
                    val = 2.0 * rand + (1.0 - 2.0 * rand) * (xy ** (eta + 1))
                    deltaq = val ** (1.0 / (eta + 1)) - 1.0
                else:
                    xy = 1.0 - delta2
                    val = 2.0 * (1.0 - rand) + 2.0 * (rand - 0.5) * (xy ** (eta + 1))
                    deltaq = 1.0 - val ** (1.0 / (eta + 1))
                
                mutated[name] = max(low, min(high, value + deltaq * (high - low)))
            else:
                mutated[name] = value
        
        return mutated
    
    def initialize_population(self) -> List[Dict[str, float]]:
        """Initialize random population."""
        self.population = [
            (self._random_individual(), None)
            for _ in range(self.population_size)
        ]
        return [ind[0] for ind in self.population]
    
    def observe(
        self,
        params: Dict[str, float],
        objectives: Dict[str, float],
    ) -> None:
        """Record an observation."""
        # Find and update in population
        for i, (p, _) in enumerate(self.population):
            if all(abs(p.get(k, 0) - params.get(k, 0)) < 1e-10 for k in self.param_names):
                self.population[i] = (params, objectives)
                break
        else:
            # Add as new
            self.population.append((params, objectives))
        
        # Update Pareto frontier
        self._update_pareto_frontier()
    
    def _update_pareto_frontier(self) -> None:
        """Update the Pareto frontier."""
        evaluated = [(p, o) for p, o in self.population if o is not None]
        if not evaluated:
            return
        
        fronts = self._non_dominated_sort(evaluated)
        if fronts:
            self.pareto_frontier = [evaluated[i] for i in fronts[0]]
    
    def evolve(self) -> List[Dict[str, float]]:
        """
        Evolve population and return new candidates.
        
        Returns candidates that need to be evaluated.
        """
        self.generation += 1
        
        # Get evaluated population
        evaluated = [(p, o) for p, o in self.population if o is not None]
        
        if len(evaluated) < 4:
            # Not enough evaluated, propose random
            return [self._random_individual() for _ in range(self.population_size // 2)]
        
        # Non-dominated sorting
        fronts = self._non_dominated_sort(evaluated)
        
        # Select parents using tournament selection with crowding
        parents = []
        for front in fronts:
            if len(parents) >= self.population_size:
                break
            
            distances = self._crowding_distance(front, evaluated)
            ranked = sorted(zip(front, distances), key=lambda x: -x[1])
            
            for idx, _ in ranked:
                if len(parents) >= self.population_size:
                    break
                parents.append(evaluated[idx][0])
        
        # Generate offspring
        offspring = []
        while len(offspring) < self.population_size // 2:
            # Tournament selection
            p1_idx = self.rng.randint(0, len(parents))
            p2_idx = self.rng.randint(0, len(parents))
            parent1, parent2 = parents[p1_idx], parents[p2_idx]
            
            # Crossover
            if self.rng.random() < self.crossover_rate:
                child1, child2 = self._sbx_crossover(parent1, parent2)
            else:
                child1, child2 = parent1.copy(), parent2.copy()
            
            # Mutation
            child1 = self._polynomial_mutation(child1)
            child2 = self._polynomial_mutation(child2)
            
            offspring.extend([child1, child2])
        
        # Add offspring to population
        for child in offspring:
            self.population.append((child, None))
        
        return offspring
    
    def get_pareto_frontier(self) -> List[Tuple[Dict[str, float], Dict[str, float]]]:
        """Get current Pareto frontier."""
        return self.pareto_frontier
