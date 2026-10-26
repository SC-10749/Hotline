from __future__ import annotations

import json
import re
import time
import urllib.request
import urllib.request
from typing import Any
from uuid import uuid4

from .config import Settings


class PgVectorStore:
    """Small pgvector adapter matching the Java vector_file_info store."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._connection = None
        self._retry_after = 0.0
        # Why the store is unusable right now; surfaced by the vectorise endpoint so a
        # misconfigured pgvector reads as "check DODO_VECTOR_*" instead of a dead server.
        self.error = ""
        if settings.vector_enabled:
            self._connect()

    def _connect(self) -> bool:
        """Open pgvector and build the schema, lazily and without ever raising."""
        if self._connection is not None:
            return True
        if not self.settings.vector_enabled:
            self.error = "DODO_VECTOR_ENABLED 未开启"
            return False
        # An unreachable pgvector must not put a connect timeout behind every chat turn,
        # so a failure is remembered for a moment; `ready()` clears it for explicit calls.
        if time.time() < self._retry_after:
            return False
        try:
            import psycopg
        except ImportError:
            self.error = "已启用向量库但未安装 psycopg"
            return False
        settings = self.settings
        try:
            self._connection = psycopg.connect(
                host=settings.vector_host, port=settings.vector_port, dbname=settings.vector_database,
                user=settings.vector_user, password=settings.vector_password,
                connect_timeout=5, autocommit=True,
            )
            self._initialise()
            self.error = ""
            self._retry_after = 0.0
            return True
        except Exception as exc:
            self._connection = None
            self._retry_after = time.time() + 30
            self.error = (str(exc).strip() or type(exc).__name__).splitlines()[0]
            return False

    def _initialise(self) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute(f"""CREATE TABLE IF NOT EXISTS {self._table} (
                id uuid PRIMARY KEY, content text, metadata jsonb, embedding vector({self.settings.vector_dimension})
            )""")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {self._table}_embedding_hnsw ON {self._table} USING hnsw (embedding vector_cosine_ops)")
            # Parents carry no embedding by design: they exist so a recalled child
            # can be expanded back to its whole section before reaching the LLM.
            cursor.execute(f"""CREATE TABLE IF NOT EXISTS {self._parent_table} (
                id uuid PRIMARY KEY, file_id text, heading text, content text, skip_embedding boolean DEFAULT true
            )""")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {self._parent_table}_file_id_idx ON {self._parent_table} (file_id)")
            cursor.execute("""CREATE TABLE IF NOT EXISTS dodo_knowledge_relation (
                id bigserial PRIMARY KEY, file_id text NOT NULL, subject text NOT NULL,
                predicate text NOT NULL, object text NOT NULL, evidence text NOT NULL
            )""")
            cursor.execute("CREATE INDEX IF NOT EXISTS dodo_knowledge_relation_file_idx ON dodo_knowledge_relation (file_id)")

    def ready(self) -> bool:
        """Whether vectorisation can run right now, with `error` explaining why not."""
        if not self.settings.embedding_api_key:
            self.error = "未配置 Embedding Key（DASHSCOPE_API_KEY 或 DODO_EMBEDDING_API_KEY）"
            return False
        self._retry_after = 0.0
        return self._connect()

    @property
    def _table(self) -> str:
        table = self.settings.vector_table
        if not table.replace("_", "").isalnum():
            raise ValueError("Invalid vector table name")
        return table

    @property
    def _parent_table(self) -> str:
        table = self.settings.vector_parent_table
        if not table.replace("_", "").isalnum():
            raise ValueError("Invalid parent table name")
        return table

    def _embed(self, text: str) -> list[float]:
        if not self.settings.embedding_api_key:
            raise RuntimeError("Embedding API key is not configured")
        endpoint = self.settings.embedding_base_url.rstrip("/") + "/embeddings"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps({"model": self.settings.embedding_model, "input": text}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.settings.embedding_api_key}"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode())["data"][0]["embedding"]

    def add_chunks(self, file_id: str, chunks: list[str]) -> None:
        if not chunks or not self.settings.embedding_api_key or not self._connect():
            return
        with self._connection.cursor() as cursor:
            for index, text in enumerate(chunks):
                vector = self._embed(text)
                cursor.execute(
                    f"INSERT INTO {self._table} (id,content,metadata,embedding) VALUES (%s,%s,%s,%s::vector)",
                    (str(uuid4()), text, json.dumps({"fileid": file_id, "chunkId": index}), self._vector_literal(vector)),
                )

    def search(self, file_id: str, question: str, top_k: int = 5) -> list[str]:
        if not self.settings.embedding_api_key or not self._connect():
            return []
        vector = self._embed(question)
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT content FROM {self._table} WHERE metadata->>'fileid'=%s ORDER BY embedding <=> %s::vector LIMIT %s",
                (file_id, self._vector_literal(vector), top_k),
            )
            return [row[0] for row in cursor.fetchall()]

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(str(value) for value in vector) + "]"

    def index_document(self, parents: list, children: list) -> int:
        """Store parents unembedded and vectorise the children under them."""
        if not self._connect():
            return 0
        with self._connection.cursor() as cursor:
            for parent in parents:
                cursor.execute(
                    f"INSERT INTO {self._parent_table} (id, file_id, heading, content, skip_embedding) "
                    "VALUES (%s, %s, %s, %s, true) ON CONFLICT (id) DO UPDATE SET content=excluded.content",
                    (parent.id, parent.fileId, parent.heading, parent.content),
                )
            stored = 0
            for child in children:
                cursor.execute(
                    f"INSERT INTO {self._table} (id, content, metadata, embedding) VALUES (%s, %s, %s::jsonb, %s::vector)",
                    (child.id, child.content,
                     json.dumps({"fileid": child.fileId, "chunkId": child.index,
                                 "parentChunkId": child.parentId, "heading": child.heading}),
                     self._vector_literal(self._embed(child.content))),
                )
                stored += 1
        return stored

    def search_expanded(self, file_id: str, question: str, top_k: int = 5) -> list[str]:
        """Recall children, then hand the LLM the whole parent section when there is one."""
        if not self.settings.embedding_api_key or not self._connect():
            return []
        vector = self._embed(question)
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT c.content, c.metadata->>'parentChunkId' AS parent_id
                    FROM {self._table} c WHERE c.metadata->>'fileid' = %s
                    ORDER BY c.embedding <=> %s::vector LIMIT %s""",
                (file_id, self._vector_literal(vector), top_k),
            )
            hits = cursor.fetchall()
            parent_ids = [row[1] for row in hits if row[1]]
            parents = {}
            if parent_ids:
                cursor.execute(
                    f"SELECT id, content FROM {self._parent_table} WHERE id = ANY(%s)", (parent_ids,))
                parents = {row[0]: row[1] for row in cursor.fetchall()}
        expanded: list[str] = []
        for content, parent_id in hits:
            expanded.append(parents.get(parent_id) or content)
        return expanded

    @staticmethod
    def _terms(query: str) -> list[str]:
        terms = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", query)
        return list(dict.fromkeys(terms))[:8]

    def search_keyword(self, file_id: str, question: str, top_k: int = 5) -> list[str]:
        """Substring keyword retrieval; works for Chinese text without a tokenizer extension."""
        terms = self._terms(question)
        if not terms or not self._connect():
            return []
        predicates = " OR ".join("c.content ILIKE %s" for _ in terms)
        params = (file_id, *(f"%{term}%" for term in terms), top_k)
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT c.content, c.metadata->>'parentChunkId' FROM {self._table} c "
                f"WHERE c.metadata->>'fileid' = %s AND ({predicates}) LIMIT %s",
                params,
            )
            hits = cursor.fetchall()
            parent_ids = [row[1] for row in hits if row[1]]
            parents = {}
            if parent_ids:
                cursor.execute(f"SELECT id, content FROM {self._parent_table} WHERE id = ANY(%s)", (parent_ids,))
                parents = {row[0]: row[1] for row in cursor.fetchall()}
        return list(dict.fromkeys(parents.get(parent_id) or content for content, parent_id in hits))

    def search_graph(self, file_id: str, question: str, top_k: int = 5) -> list[str]:
        terms = self._terms(question)
        if not terms or not self._connect():
            return []
        predicates = " OR ".join("subject ILIKE %s OR object ILIKE %s OR predicate ILIKE %s" for _ in terms)
        params = tuple(value for term in terms for value in (f"%{term}%",) * 3)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT subject, predicate, object, evidence FROM dodo_knowledge_relation "
                f"WHERE file_id = %s AND ({predicates}) LIMIT %s",
                (file_id, *params, top_k),
            )
            rows = cursor.fetchall()
        return [f"图谱关系：{subject} -[{predicate}]-> {obj}\n来源：{evidence}"
                for subject, predicate, obj, evidence in rows]

    def search_text2sql(self, file_id: str, generated_sql: str, top_k: int = 8) -> list[str]:
        """Execute only a narrow SELECT over this document's chunks; model SQL is never run raw."""
        if not self._connect():
            return []
        table = self._table
        pattern = re.compile(
            rf"\s*SELECT\s+content\s+FROM\s+{re.escape(table)}\s+"
            r"WHERE\s+metadata\s*->>\s*'fileid'\s*=\s*:file_id"
            r"(?:\s+AND\s+content\s+ILIKE\s+'((?:[^']|'')*)')?"
            r"(?:\s+LIMIT\s+(\d+))?\s*\Z",
            re.IGNORECASE,
        )
        match = pattern.fullmatch(generated_sql or "")
        if not match:
            raise ValueError("Text2SQL 仅允许查询当前文档分段表的 content，并必须使用 :file_id 过滤")
        clause, requested_limit = match.groups()
        limit = min(int(requested_limit or top_k), top_k, 20)
        sql = f"SELECT content FROM {table} WHERE metadata->>'fileid' = %s"
        params: list[Any] = [file_id]
        if clause is not None:
            sql += " AND content ILIKE %s"
            params.append(clause.replace("''", "'").replace("%", "\\%").replace("_", "\\_"))
            params[-1] = f"%{params[-1]}%" if not (params[-1].startswith("%") and params[-1].endswith("%")) else params[-1]
        sql += " LIMIT %s"
        params.append(limit)
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            return [row[0] for row in cursor.fetchall()]

    def replace_graph(self, file_id: str, relations: list[dict[str, str]]) -> int:
        if not self._connect():
            return 0
        with self._connection.cursor() as cursor:
            cursor.execute("DELETE FROM dodo_knowledge_relation WHERE file_id = %s", (file_id,))
            for relation in relations:
                subject = str(relation.get("subject", "")).strip()[:200]
                predicate = str(relation.get("predicate", "")).strip()[:100]
                obj = str(relation.get("object", "")).strip()[:200]
                evidence = str(relation.get("evidence", "")).strip()[:3000]
                if subject and predicate and obj and evidence:
                    cursor.execute(
                        "INSERT INTO dodo_knowledge_relation (file_id, subject, predicate, object, evidence) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (file_id, subject, predicate, obj, evidence),
                    )
        return len(relations)

    def delete_document(self, file_id: str) -> None:
        if not self._connect():
            return
        with self._connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {self._table} WHERE metadata->>'fileid' = %s", (file_id,))
            cursor.execute(f"DELETE FROM {self._parent_table} WHERE file_id = %s", (file_id,))
            cursor.execute("DELETE FROM dodo_knowledge_relation WHERE file_id = %s", (file_id,))
