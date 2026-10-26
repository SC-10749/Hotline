from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlparse

from .config import Settings


class ObjectStorage:
    """MinIO adapter with an explicit local development implementation."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.backend = settings.file_storage_backend
        self.client = None
        if self.backend == "minio":
            try:
                from minio import Minio
            except ImportError as exc:
                raise RuntimeError(
                    "MinIO storage is enabled but the minio package is not installed"
                ) from exc

            endpoint = urlparse(settings.minio_endpoint)
            host = endpoint.netloc or endpoint.path
            self.client = Minio(
                host,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=endpoint.scheme == "https",
            )
        elif self.backend != "local":
            raise ValueError("DODO_FILE_STORAGE_BACKEND must be minio or local")

    def _ensure_bucket(self) -> None:
        assert self.client is not None
        bucket = self.settings.minio_bucket
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)
        if self.settings.minio_public_read:
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{bucket}/*"],
                    }
                ],
            }
            self.client.set_bucket_policy(bucket, json.dumps(policy))

    def _local_path(self, object_name: str) -> Path:
        root = self.settings.upload_dir.resolve()
        target = (root / object_name).resolve()
        if target != root and root not in target.parents:
            raise ValueError("Invalid object name")
        return target

    def upload_bytes(self, content: bytes, object_name: str, content_type: str) -> str:
        if not object_name or object_name.startswith("/"):
            raise ValueError("Object name cannot be empty or absolute")

        if self.backend == "local":
            target = self._local_path(object_name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return f"local://{object_name}"

        assert self.client is not None
        self._ensure_bucket()
        self.client.put_object(
            self.settings.minio_bucket,
            object_name,
            BytesIO(content),
            length=len(content),
            content_type=content_type or "application/octet-stream",
        )
        endpoint = self.settings.minio_endpoint.rstrip("/")
        return f"{endpoint}/{self.settings.minio_bucket}/{quote(object_name, safe='/')}"

    def delete_url(self, url: str | None) -> None:
        if not url:
            return
        object_name = self.object_name(url)
        if not object_name:
            return
        if self.backend == "local":
            self._local_path(object_name).unlink(missing_ok=True)
            return
        assert self.client is not None
        self.client.remove_object(self.settings.minio_bucket, object_name)

    def public_url(self, url: str, object_name: str) -> str:
        """Address an object the way a browser would reach it.

        MinIO hands back a real URL; the local backend only knows a file path, so
        images referenced from converted markdown go through this service.
        """
        if not url.startswith("local://"):
            return url
        return f"/doc-asset/{quote(object_name, safe='/')}"

    def object_name(self, url: str) -> str:
        if url.startswith("local://"):
            return url.removeprefix("local://")
        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
        bucket_prefix = self.settings.minio_bucket + "/"
        if path.startswith(bucket_prefix):
            return path.removeprefix(bucket_prefix)
        return path

