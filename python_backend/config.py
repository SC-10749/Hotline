from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


_storage_backend = os.getenv("DODO_STORAGE_BACKEND", "mysql").strip().lower()


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("DODO_HOST", "0.0.0.0")
    port: int = int(os.getenv("DODO_PORT", "8888"))

    # The production backend intentionally follows the Java service. SQLite and
    # local files are available only when explicitly selected for development.
    storage_backend: str = _storage_backend
    file_storage_backend: str = os.getenv(
        "DODO_FILE_STORAGE_BACKEND",
        "minio" if _storage_backend == "mysql" else "local",
    ).strip().lower()

    data_dir: Path = Path(os.getenv("DODO_DATA_DIR", "data"))
    upload_dir: Path = Path(os.getenv("DODO_UPLOAD_DIR", "data/uploads"))
    generated_dir: Path = Path(os.getenv("DODO_GENERATED_DIR", "data/generated"))
    skills_dir: Path = Path(os.getenv("SKILLS_DIRECTORY", "data/skills"))
    repo_skills_dir: Path = Path(os.getenv("DODO_REPO_SKILLS_DIRECTORY", str(Path(__file__).resolve().parents[1] / "skills")))
    skill_catalog_db: Path = Path(os.getenv("DODO_SKILL_CATALOG_DB", "data/skill-center/catalog.db"))
    skill_project: str = os.getenv("DODO_SKILL_PROJECT", "dodo-agent")
    max_file_size: int = int(os.getenv("DODO_MAX_FILE_SIZE", str(50 * 1024 * 1024)))
    max_text_length: int = int(os.getenv("DODO_MAX_TEXT_LENGTH", "20000"))
    large_file_threshold: int = int(os.getenv("DODO_LARGE_FILE_THRESHOLD", "5000"))
    chunk_size: int = int(os.getenv("DODO_CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("DODO_CHUNK_OVERLAP", "100"))
    # Fallback sweep for documents that never got vectorised; 0 disables the in-process timer.
    doc_compensate_interval: int = int(os.getenv("DODO_DOC_COMPENSATE_INTERVAL", "300"))

    # MySQL settings mirror spring.datasource from application.yml.
    mysql_host: str = os.getenv("DODO_MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("DODO_MYSQL_PORT", "3306"))
    mysql_database: str = os.getenv("DODO_MYSQL_DATABASE", "dodo")
    mysql_user: str = os.getenv("DODO_MYSQL_USER", "root")
    mysql_password: str = os.getenv("DODO_MYSQL_PASSWORD", "root")
    mysql_pool_size: int = int(os.getenv("DODO_MYSQL_POOL_SIZE", "20"))

    # Redis backs the distributed agent task lock and stop broadcast.
    redis_enabled: bool = _bool_env("DODO_REDIS_ENABLED", _storage_backend == "mysql")
    redis_host: str = os.getenv("DODO_REDIS_HOST", "127.0.0.1")
    redis_port: int = int(os.getenv("DODO_REDIS_PORT", "6379"))
    redis_database: int = int(os.getenv("DODO_REDIS_DATABASE", "0"))
    redis_password: str = os.getenv("DODO_REDIS_PASSWORD", "")
    redis_timeout: float = float(os.getenv("DODO_REDIS_TIMEOUT", "5"))
    redis_task_ttl: int = int(os.getenv("DODO_REDIS_TASK_TTL", str(30 * 60)))

    # MinIO settings mirror minio.* from application.yml.
    minio_endpoint: str = os.getenv("DODO_MINIO_ENDPOINT", "http://127.0.0.1:9000")
    minio_access_key: str = os.getenv("DODO_MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("DODO_MINIO_SECRET_KEY", "minioadmin")
    minio_bucket: str = os.getenv("DODO_MINIO_BUCKET", "rag-test2")
    minio_public_read: bool = _bool_env("DODO_MINIO_PUBLIC_READ", True)

    # pgvector settings mirror embeddings.store and DynamicPgVectorStoreFactory.
    vector_enabled: bool = _bool_env("DODO_VECTOR_ENABLED", _storage_backend == "mysql")
    vector_host: str = os.getenv("DODO_VECTOR_HOST", "127.0.0.1")
    vector_port: int = int(os.getenv("DODO_VECTOR_PORT", "5432"))
    vector_database: str = os.getenv("DODO_VECTOR_DATABASE", "vector_store")
    vector_user: str = os.getenv("DODO_VECTOR_USER", "postgres")
    vector_password: str = os.getenv("DODO_VECTOR_PASSWORD", "postgres")
    vector_table: str = os.getenv("DODO_VECTOR_TABLE", "vector_file_info")
    vector_parent_table: str = os.getenv("DODO_VECTOR_PARENT_TABLE", "document_parent_chunk")
    vector_dimension: int = int(os.getenv("DODO_VECTOR_DIMENSION", "1024"))

    model_api_key: str = (
        os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("OPENAI_API_KEY", "")
    )
    model_base_url: str = os.getenv(
        "OPENAI_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    model_name: str = os.getenv("DODO_MODEL", "qwen-plus")
    embedding_api_key: str = (
        os.getenv("DODO_EMBEDDING_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("OPENAI_API_KEY", "")
    )
    embedding_base_url: str = os.getenv(
        "DODO_EMBEDDING_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    embedding_model: str = os.getenv("DODO_EMBEDDING_MODEL", "text-embedding-v4")
    # MinerU precision-extract API. Local documents are uploaded through a
    # presigned URL, so the token only authorises the task calls themselves.
    mineru_token: str = os.getenv("MINERU_TOKEN", "")
    mineru_base_url: str = os.getenv("DODO_MINERU_BASE_URL", "https://mineru.net")
    mineru_model_version: str = os.getenv("DODO_MINERU_MODEL_VERSION", "vlm")
    mineru_poll_interval: float = float(os.getenv("DODO_MINERU_POLL_INTERVAL", "5"))
    mineru_timeout: int = int(os.getenv("DODO_MINERU_TIMEOUT", "900"))

    # Multimodal captioning for images MinerU extracts out of the document.
    # It cannot ride on the chat model: DeepSeek has no vision endpoint, and a
    # localhost image URL is unreachable for a hosted model, so images ship as
    # base64 data URLs instead.
    multimodal_model: str = os.getenv("DODO_MULTIMODAL_MODEL", "qwen3-vl-plus")
    multimodal_base_url: str = os.getenv(
        "DODO_MULTIMODAL_BASE_URL",
        os.getenv("DODO_EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )
    multimodal_api_key: str = (
        os.getenv("DODO_MULTIMODAL_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY", "")
    )
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "dodo.db"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.upload_dir, self.generated_dir, self.skills_dir):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
