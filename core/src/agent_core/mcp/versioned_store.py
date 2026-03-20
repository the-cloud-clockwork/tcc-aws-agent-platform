"""Versioned S3 artifact store.

Generic S3 versioned artifact pattern — extracted from ml-predict model
loader. Handles version pointers, byte-level load/store, JSON convenience,
and in-memory caching for warm Lambda reuse.

Domain MCPs handle their own deserialization on the ``bytes`` returned.

S3 layout::

    {artifact_id}/{version}/{filename}
    {artifact_id}/latest               ← contains version string
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_s3_override: Any = None


def _override_s3_client(client: Any) -> None:
    """Override S3 client for testing (e.g. moto)."""
    global _s3_override
    _s3_override = client


class VersionedS3Store:
    """Versioned artifact storage backed by S3.

    Args:
        bucket_env_var: Environment variable name that holds the bucket name.
        default_bucket: Fallback bucket name if env var is unset.
    """

    def __init__(self, bucket_env_var: str, default_bucket: str = "") -> None:
        self._bucket_env_var = bucket_env_var
        self._default_bucket = default_bucket
        self._cache: dict[str, bytes] = {}

    @property
    def bucket(self) -> str:
        return os.environ.get(self._bucket_env_var, self._default_bucket)

    def _s3(self) -> Any:
        if _s3_override is not None:
            return _s3_override
        import boto3
        return boto3.client("s3")

    def get_latest_version(self, artifact_id: str) -> str:
        """Fetch the latest version string for an artifact.

        Reads ``s3://{bucket}/{artifact_id}/latest``.
        Falls back to ``"v1"`` if the pointer is missing.
        """
        try:
            resp = self._s3().get_object(
                Bucket=self.bucket,
                Key=f"{artifact_id}/latest",
            )
            version = resp["Body"].read().decode("utf-8").strip()
            logger.info("Latest version for %s: %s", artifact_id, version)
            return version
        except Exception:
            logger.warning(
                "Could not fetch latest version for %s, defaulting to v1", artifact_id
            )
            return "v1"

    def load_bytes(
        self,
        artifact_id: str,
        filename: str,
        version: str | None = None,
    ) -> bytes:
        """Load raw bytes from S3.

        Uses an in-memory cache keyed by ``{artifact_id}/{version}/{filename}``
        to avoid re-downloading on warm Lambda invocations.
        """
        if version is None:
            version = self.get_latest_version(artifact_id)

        cache_key = f"{artifact_id}/{version}/{filename}"
        if cache_key in self._cache:
            logger.debug("Store cache hit: %s", cache_key)
            return self._cache[cache_key]

        s3_key = f"{artifact_id}/{version}/{filename}"
        logger.info("Loading from s3://%s/%s", self.bucket, s3_key)

        resp = self._s3().get_object(Bucket=self.bucket, Key=s3_key)
        data = resp["Body"].read()
        self._cache[cache_key] = data
        return data

    def load_json(
        self,
        artifact_id: str,
        filename: str = "metadata.json",
        version: str | None = None,
    ) -> dict:
        """Load and parse a JSON file from S3."""
        data = self.load_bytes(artifact_id, filename, version)
        return json.loads(data.decode("utf-8"))

    def store(
        self,
        artifact_id: str,
        version: str,
        files: dict[str, bytes],
        *,
        set_latest: bool = True,
    ) -> str:
        """Store files to S3 under ``{artifact_id}/{version}/``.

        Args:
            artifact_id: Artifact identifier (e.g. "classifier_model_v2").
            version: Version string (e.g. "v2").
            files: Mapping of filename → bytes content.
            set_latest: If True, update the ``latest`` pointer.

        Returns:
            S3 path prefix where files were stored.
        """
        bucket = self.bucket
        prefix = f"{artifact_id}/{version}"

        for filename, content in files.items():
            self._s3().put_object(
                Bucket=bucket,
                Key=f"{prefix}/{filename}",
                Body=content,
            )

        if set_latest:
            self._s3().put_object(
                Bucket=bucket,
                Key=f"{artifact_id}/latest",
                Body=version.encode("utf-8"),
            )

        logger.info("Stored %d files at s3://%s/%s/", len(files), bucket, prefix)
        return f"s3://{bucket}/{prefix}/"

    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()
        logger.info("Store cache cleared")
