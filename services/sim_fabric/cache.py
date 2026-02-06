"""Caching layer for simulation results using Redis."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List

import redis

from .config import settings

logger = logging.getLogger(__name__)


class ResultCache:
    """Redis-based cache for simulation results."""

    def __init__(self, redis_client: redis.Redis | None = None):
        if redis_client:
            self._redis = redis_client
        else:
            self._redis = redis.from_url(settings.REDIS_URL)
        self._prefix = "sim_result:"
        self._ttl_seconds = settings.CACHE_TTL_SECONDS

    def _make_key(self, scenario_hash: str) -> str:
        return f"{self._prefix}{scenario_hash}"

    def compute_scenario_hash(
        self,
        domain_pack_id: str,
        domain_pack_version: str,
        state: Dict[str, Any],
        actions: Dict[str, Any],
        fidelity: str,
        seed: int,
    ) -> str:
        """Compute deterministic hash for a scenario."""
        data = {
            "domain_pack_id": domain_pack_id,
            "domain_pack_version": domain_pack_version,
            "state": state,
            "actions": actions,
            "fidelity": fidelity,
            "seed": seed,
        }
        encoded = json.dumps(data, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get(self, scenario_hash: str) -> Dict[str, Any] | None:
        """Get cached result for a scenario hash."""
        key = self._make_key(scenario_hash)
        try:
            data = self._redis.get(key)
            if data:
                logger.debug(f"Cache hit for {scenario_hash[:12]}")
                return json.loads(data)
        except Exception as exc:
            logger.warning(f"Cache get failed: {exc}")
        return None

    def set(self, scenario_hash: str, result: Dict[str, Any]) -> bool:
        """Cache a simulation result."""
        key = self._make_key(scenario_hash)
        try:
            encoded = json.dumps(result, default=str)
            self._redis.setex(key, self._ttl_seconds, encoded)
            logger.debug(f"Cached result for {scenario_hash[:12]}")
            return True
        except Exception as exc:
            logger.warning(f"Cache set failed: {exc}")
            return False

    def get_batch(
        self, scenario_hashes: List[str]
    ) -> Dict[str, Dict[str, Any] | None]:
        """Get multiple cached results."""
        results: Dict[str, Dict[str, Any] | None] = {}
        if not scenario_hashes:
            return results

        try:
            keys = [self._make_key(h) for h in scenario_hashes]
            values = self._redis.mget(keys)
            for scenario_hash, value in zip(scenario_hashes, values, strict=False):
                if value:
                    results[scenario_hash] = json.loads(value)
                else:
                    results[scenario_hash] = None
        except Exception as exc:
            logger.warning(f"Cache batch get failed: {exc}")
            for scenario_hash in scenario_hashes:
                results[scenario_hash] = None

        return results

    def invalidate(self, scenario_hash: str) -> bool:
        """Invalidate a cached result."""
        key = self._make_key(scenario_hash)
        try:
            self._redis.delete(key)
            return True
        except Exception as exc:
            logger.warning(f"Cache invalidate failed: {exc}")
            return False

    def clear_all(self) -> int:
        """Clear all cached simulation results."""
        try:
            pattern = f"{self._prefix}*"
            keys = list(self._redis.scan_iter(match=pattern))
            if keys:
                return self._redis.delete(*keys)
            return 0
        except Exception as exc:
            logger.warning(f"Cache clear failed: {exc}")
            return 0


# Global instance
_cache: ResultCache | None = None


def get_result_cache() -> ResultCache:
    """Get global result cache instance."""
    global _cache
    if _cache is None:
        _cache = ResultCache()
    return _cache
