"""Tracing and metrics for simulation jobs."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generator

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Prometheus metrics
SIMULATION_DURATION = Histogram(
    "sim_fabric_simulation_duration_seconds",
    "Simulation execution duration in seconds",
    ["domain_pack", "fidelity", "status"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

SIMULATION_COUNTER = Counter(
    "sim_fabric_simulations_total",
    "Total number of simulations run",
    ["domain_pack", "fidelity", "status"],
)

ACTIVE_SIMULATIONS = Gauge(
    "sim_fabric_active_simulations",
    "Number of currently running simulations",
    ["domain_pack"],
)

INVARIANT_VIOLATIONS = Counter(
    "sim_fabric_invariant_violations_total",
    "Total number of invariant violations detected",
    ["domain_pack", "check_name"],
)

CACHE_HITS = Counter(
    "sim_fabric_cache_hits_total",
    "Total number of cache hits",
    ["domain_pack"],
)

CACHE_MISSES = Counter(
    "sim_fabric_cache_misses_total",
    "Total number of cache misses",
    ["domain_pack"],
)

ARTIFACT_SIZE_BYTES = Histogram(
    "sim_fabric_artifact_size_bytes",
    "Size of stored artifacts in bytes",
    ["artifact_type"],
    buckets=[1e3, 1e4, 1e5, 1e6, 1e7, 1e8],
)


@dataclass
class SpanContext:
    """Context for a tracing span."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    operation_name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: list[Dict[str, Any]] = field(default_factory=list)

    def log(self, message: str, **kwargs: Any) -> None:
        self.logs.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": message,
                **kwargs,
            }
        )

    def set_tag(self, key: str, value: Any) -> None:
        self.tags[key] = value

    def finish(self) -> None:
        self.end_time = time.time()

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "tags": self.tags,
            "logs": self.logs,
        }


class JobTracer:
    """Tracer for simulation jobs."""

    def __init__(self):
        self._active_spans: Dict[str, SpanContext] = {}

    def start_trace(self, operation_name: str) -> SpanContext:
        """Start a new trace."""
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        span = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            operation_name=operation_name,
        )
        self._active_spans[span_id] = span
        return span

    def start_span(
        self,
        operation_name: str,
        parent: SpanContext | None = None,
    ) -> SpanContext:
        """Start a new span, optionally under a parent."""
        trace_id = parent.trace_id if parent else str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        parent_span_id = parent.span_id if parent else None

        span = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
        )
        self._active_spans[span_id] = span
        return span

    def finish_span(self, span: SpanContext) -> None:
        """Finish a span."""
        span.finish()
        self._active_spans.pop(span.span_id, None)
        logger.debug(
            f"Span finished: {span.operation_name} "
            f"duration={span.duration_seconds:.3f}s"
        )

    @contextmanager
    def trace(
        self,
        operation_name: str,
        parent: SpanContext | None = None,
    ) -> Generator[SpanContext, None, None]:
        """Context manager for tracing an operation."""
        span = self.start_span(operation_name, parent)
        try:
            yield span
        except Exception as exc:
            span.set_tag("error", True)
            span.set_tag("error_message", str(exc))
            raise
        finally:
            self.finish_span(span)


def record_simulation_metrics(
    domain_pack: str,
    fidelity: str,
    status: str,
    duration_seconds: float,
) -> None:
    """Record Prometheus metrics for a simulation."""
    SIMULATION_COUNTER.labels(
        domain_pack=domain_pack,
        fidelity=fidelity,
        status=status,
    ).inc()
    SIMULATION_DURATION.labels(
        domain_pack=domain_pack,
        fidelity=fidelity,
        status=status,
    ).observe(duration_seconds)


def record_invariant_violation(domain_pack: str, check_name: str) -> None:
    """Record an invariant violation."""
    INVARIANT_VIOLATIONS.labels(
        domain_pack=domain_pack,
        check_name=check_name,
    ).inc()


def record_cache_hit(domain_pack: str) -> None:
    """Record a cache hit."""
    CACHE_HITS.labels(domain_pack=domain_pack).inc()


def record_cache_miss(domain_pack: str) -> None:
    """Record a cache miss."""
    CACHE_MISSES.labels(domain_pack=domain_pack).inc()


def record_artifact_size(artifact_type: str, size_bytes: int) -> None:
    """Record artifact size."""
    ARTIFACT_SIZE_BYTES.labels(artifact_type=artifact_type).observe(size_bytes)


def increment_active_simulations(domain_pack: str) -> None:
    """Increment active simulations gauge."""
    ACTIVE_SIMULATIONS.labels(domain_pack=domain_pack).inc()


def decrement_active_simulations(domain_pack: str) -> None:
    """Decrement active simulations gauge."""
    ACTIVE_SIMULATIONS.labels(domain_pack=domain_pack).dec()


# Global tracer instance
_tracer: JobTracer | None = None


def get_tracer() -> JobTracer:
    """Get global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = JobTracer()
    return _tracer
