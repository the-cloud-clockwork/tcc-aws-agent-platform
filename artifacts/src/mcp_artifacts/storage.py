"""S3 storage operations for artifacts."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, UTC
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)

# Module-level cache for CloudFront private key
_cf_private_key: str | None = None

BUCKET_NAME = "mcp-artifacts"
SIGNED_URL_EXPIRY = 3600  # 1 hour


class ArtifactStorage:
    """Handles S3 put/get and signed URL generation."""

    def __init__(self, s3_client: S3Client | None = None, bucket: str = BUCKET_NAME) -> None:
        self._s3: S3Client = s3_client or boto3.client("s3")
        self._bucket = bucket

    def put_object(self, s3_key: str, body: bytes, content_type: str, extra_args: dict | None = None) -> None:
        """Upload bytes to S3."""
        params = {
            "Bucket": self._bucket,
            "Key": s3_key,
            "Body": body,
            "ContentType": content_type,
        }
        if extra_args:
            params.update(extra_args)
        self._s3.put_object(**params)
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

    def get_object_bytes(self, s3_key: str) -> bytes:
        """Download and return the raw bytes of an S3 object."""
        resp = self._s3.get_object(Bucket=self._bucket, Key=s3_key)
        return resp["Body"].read()

    def generate_cloudfront_signed_url(
        self,
        s3_key: str,
        expiry_days: int = 14,
    ) -> str | None:
        """Generate CloudFront signed URL if configured.

        Requires env vars:
        - CLOUDFRONT_DOMAIN
        - CLOUDFRONT_KEY_PAIR_ID
        - CLOUDFRONT_PRIVATE_KEY_SECRET_ARN (Secrets Manager ARN)

        Returns None if CloudFront not configured.
        """
        global _cf_private_key

        domain = os.environ.get("CLOUDFRONT_DOMAIN")
        if not domain:
            return None

        key_pair_id = os.environ.get("CLOUDFRONT_KEY_PAIR_ID")
        secret_arn = os.environ.get("CLOUDFRONT_PRIVATE_KEY_SECRET_ARN")
        if not key_pair_id or not secret_arn:
            logger.warning("CloudFront domain set but KEY_PAIR_ID or PRIVATE_KEY_SECRET_ARN missing")
            return None

        try:
            # Cache the private key
            if _cf_private_key is None:
                sm = boto3.client("secretsmanager")
                resp = sm.get_secret_value(SecretId=secret_arn)
                _cf_private_key = resp["SecretString"]

            from botocore.signers import CloudFrontSigner
            import rsa

            def rsa_signer(message: bytes) -> bytes:
                private_key = rsa.PrivateKey.load_pkcs1(_cf_private_key.encode())
                return rsa.sign(message, private_key, "SHA-1")

            cf_signer = CloudFrontSigner(key_pair_id, rsa_signer)
            url = f"https://{domain}/{s3_key}"
            expire_date = datetime.now(UTC) + timedelta(days=expiry_days)
            signed_url = cf_signer.generate_presigned_url(url, date_less_than=expire_date)
            return signed_url
        except Exception:
            logger.warning("CloudFront signed URL generation failed", exc_info=True)
            return None

    def get_best_url(self, s3_key: str, presign_expiry: int = 3600) -> str:
        """Return CloudFront signed URL if available, else S3 presigned URL."""
        cf_url = self.generate_cloudfront_signed_url(s3_key)
        if cf_url:
            return cf_url
        return self.generate_signed_url(s3_key, presign_expiry)
