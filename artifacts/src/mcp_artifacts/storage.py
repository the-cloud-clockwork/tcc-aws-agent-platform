"""S3 storage operations for artifacts."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)

BUCKET_NAME = "mcp-artifacts"
SIGNED_URL_EXPIRY = 3600  # 1 hour


class ArtifactStorage:
    """Handles S3 put/get and signed URL generation."""

    def __init__(self, s3_client: "S3Client | None" = None, bucket: str = BUCKET_NAME) -> None:
        self._s3: "S3Client" = s3_client or boto3.client("s3")
        self._bucket = bucket

    def put_object(self, s3_key: str, body: bytes, content_type: str) -> None:
        """Upload bytes to S3."""
        self._s3.put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=body,
            ContentType=content_type,
        )
        logger.info("Uploaded s3://%s/%s (%d bytes)", self._bucket, s3_key, len(body))

    def generate_signed_url(self, s3_key: str, expiry: int = SIGNED_URL_EXPIRY) -> str:
        """Generate a pre-signed GET URL for the given key."""
        url: str = self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": s3_key},
            ExpiresIn=expiry,
        )
        return url

    def head_object(self, s3_key: str) -> bool:
        """Check whether an object exists in S3."""
        try:
            self._s3.head_object(Bucket=self._bucket, Key=s3_key)
            return True
        except self._s3.exceptions.ClientError:
            return False
