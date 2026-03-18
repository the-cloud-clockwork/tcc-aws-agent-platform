"""S3 operations for prompt text storage."""

from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

DEFAULT_BUCKET = "prompt-registry"


class PromptStorage:
    """Read/write prompt text to S3."""

    def __init__(
        self,
        bucket: str = DEFAULT_BUCKET,
        s3_client=None,
    ) -> None:
        self.bucket = bucket
        self.s3 = s3_client or boto3.client("s3")

    def _key(self, prompt_id: str, version: str) -> str:
        return f"{prompt_id}/{version}.txt"

    def put(self, prompt_id: str, version: str, text: str) -> str:
        """Write prompt text to S3. Returns the S3 key."""
        key = self._key(prompt_id, version)
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType="text/plain",
        )
        return key

    def get(self, prompt_id: str, version: str) -> str:
        """Read prompt text from S3."""
        key = self._key(prompt_id, version)
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read().decode("utf-8")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(
                    f"Prompt text not found: {prompt_id}/{version}"
                ) from exc
            raise

    def delete(self, prompt_id: str, version: str) -> None:
        """Delete prompt text from S3."""
        key = self._key(prompt_id, version)
        self.s3.delete_object(Bucket=self.bucket, Key=key)
