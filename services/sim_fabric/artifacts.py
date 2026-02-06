"""Artifact pipeline for storing simulation outputs to MinIO."""
from __future__ import annotations

import hashlib
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
from minio import Minio
from minio.error import S3Error

from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class ArtifactRecord:
    """Record of a stored artifact."""

    object_key: str
    checksum: str
    size_bytes: int
    content_type: str
    bucket: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_key": self.object_key,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "bucket": self.bucket,
            "created_at": self.created_at,
        }


class ArtifactPipeline:
    """Handles artifact storage and retrieval from MinIO."""

    def __init__(self, client: Minio | None = None):
        if client:
            self._client = client
        else:
            self._client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=False,
            )
        self._bucket = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info(f"Created bucket: {self._bucket}")
        except S3Error as exc:
            logger.warning(f"Bucket check failed: {exc}")

    def compute_checksum(self, data: bytes) -> str:
        """Compute SHA-256 checksum of data."""
        return hashlib.sha256(data).hexdigest()

    def store_raw(
        self,
        run_id: str,
        scenario_id: str,
        name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> ArtifactRecord:
        """Store raw bytes to MinIO."""
        checksum = self.compute_checksum(data)
        object_key = f"runs/{run_id}/scenarios/{scenario_id}/{name}"

        self._client.put_object(
            self._bucket,
            object_key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
            metadata={"checksum": checksum},
        )

        return ArtifactRecord(
            object_key=object_key,
            checksum=checksum,
            size_bytes=len(data),
            content_type=content_type,
            bucket=self._bucket,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def store_json(
        self,
        run_id: str,
        scenario_id: str,
        name: str,
        data: Dict[str, Any],
    ) -> ArtifactRecord:
        """Store JSON data."""
        encoded = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        return self.store_raw(
            run_id, scenario_id, name, encoded, content_type="application/json"
        )

    def store_array(
        self,
        run_id: str,
        scenario_id: str,
        name: str,
        array: np.ndarray,
    ) -> ArtifactRecord:
        """Store numpy array as .npy file."""
        buffer = io.BytesIO()
        np.save(buffer, array)
        data = buffer.getvalue()
        return self.store_raw(
            run_id, scenario_id, f"{name}.npy", data, content_type="application/x-npy"
        )

    def store_logs(
        self,
        run_id: str,
        scenario_id: str,
        logs: List[str],
    ) -> ArtifactRecord:
        """Store simulation logs."""
        content = "\n".join(logs).encode("utf-8")
        return self.store_raw(
            run_id, scenario_id, "logs.txt", content, content_type="text/plain"
        )

    def downsample_array(
        self,
        array: np.ndarray,
        target_size: int | None = None,
    ) -> np.ndarray:
        target_size = target_size or settings.PREVIEW_TARGET_SIZE
        """Downsample a 2D array for preview."""
        if array.ndim != 2:
            return array

        h, w = array.shape
        if h <= target_size and w <= target_size:
            return array

        factor_h = max(1, h // target_size)
        factor_w = max(1, w // target_size)

        # Simple block averaging
        new_h = h // factor_h
        new_w = w // factor_w
        trimmed = array[: new_h * factor_h, : new_w * factor_w]
        reshaped = trimmed.reshape(new_h, factor_h, new_w, factor_w)
        downsampled = reshaped.mean(axis=(1, 3))
        return downsampled

    def generate_heatmap_png(
        self,
        array: np.ndarray,
        colormap: str | None = None,
    ) -> bytes:
        colormap = colormap or settings.HEATMAP_COLORMAP
        """Generate a PNG heatmap from a 2D array."""
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib not available for heatmap generation")
            return b""

        fig, ax = plt.subplots(figsize=(8, 6))
        im = ax.imshow(array, cmap=colormap, aspect="auto")
        plt.colorbar(im, ax=ax)
        ax.set_title("Simulation Heatmap")

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
        plt.close(fig)
        buffer.seek(0)
        return buffer.read()

    def generate_tiles(
        self,
        array: np.ndarray,
        tile_size: int = 256,
    ) -> List[Dict[str, Any]]:
        """Generate tile metadata for a large array."""
        if array.ndim != 2:
            return []

        h, w = array.shape
        tiles = []
        tile_y = 0

        for y in range(0, h, tile_size):
            tile_x = 0
            for x in range(0, w, tile_size):
                tile_h = min(tile_size, h - y)
                tile_w = min(tile_size, w - x)
                tiles.append(
                    {
                        "tile_x": tile_x,
                        "tile_y": tile_y,
                        "x_start": x,
                        "y_start": y,
                        "width": tile_w,
                        "height": tile_h,
                    }
                )
                tile_x += 1
            tile_y += 1

        return tiles

    def store_preview(
        self,
        run_id: str,
        scenario_id: str,
        array: np.ndarray,
        name: str = "preview",
    ) -> List[ArtifactRecord]:
        """Store downsampled preview and PNG heatmap."""
        records = []

        # Downsampled array
        downsampled = self.downsample_array(array)
        records.append(
            self.store_array(run_id, scenario_id, f"{name}_downsampled", downsampled)
        )

        # PNG heatmap
        png_data = self.generate_heatmap_png(downsampled)
        if png_data:
            records.append(
                self.store_raw(
                    run_id,
                    scenario_id,
                    f"{name}.png",
                    png_data,
                    content_type="image/png",
                )
            )

        return records

    def store_simulation_output(
        self,
        run_id: str,
        scenario_id: str,
        outcome: Dict[str, Any],
    ) -> List[ArtifactRecord]:
        """Store complete simulation output with all artifacts."""
        records: List[ArtifactRecord] = []

        # Store outcome JSON
        records.append(self.store_json(run_id, scenario_id, "outcome.json", outcome))

        # Store arrays with previews
        arrays = outcome.get("arrays", {})
        for array_name, array_data in arrays.items():
            if array_data is None:
                continue
            try:
                arr = np.array(array_data)
                # Full array
                records.append(self.store_array(run_id, scenario_id, array_name, arr))
                # Preview (for 2D arrays)
                if arr.ndim == 2:
                    records.extend(
                        self.store_preview(run_id, scenario_id, arr, f"{array_name}_preview")
                    )
            except Exception as exc:
                logger.warning(f"Failed to store array {array_name}: {exc}")

        # Store logs if present
        logs = outcome.get("logs", [])
        if logs:
            records.append(self.store_logs(run_id, scenario_id, logs))

        return records

    def fetch(self, object_key: str) -> bytes:
        """Fetch an artifact from MinIO."""
        response = self._client.get_object(self._bucket, object_key)
        data = response.read()
        response.close()
        response.release_conn()
        return data

    def exists(self, object_key: str) -> bool:
        """Check if an artifact exists."""
        try:
            self._client.stat_object(self._bucket, object_key)
            return True
        except S3Error:
            return False


# Global instance
_pipeline: ArtifactPipeline | None = None


def get_artifact_pipeline() -> ArtifactPipeline:
    """Get global artifact pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = ArtifactPipeline()
    return _pipeline
