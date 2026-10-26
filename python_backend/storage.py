from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from .config import Settings
from .models import DocumentRecord, FileInfo, SessionMessage, now_iso


class Storage:
    """Persistence adapter for the Java schema, with an explicit SQLite fallback."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.backend = settings.storage_backend
        self._lock = threading.RLock()
        self._mysql_pool = None
        if self.backend == "mysql":
            try:
                from mysql.connector.pooling import MySQLConnectionPool
            except ImportError as exc:
                raise RuntimeError("MySQL storage is enabled but mysql-connector-python is not installed") from exc
            self._mysql_pool = MySQLConnectionPool(
                pool_name="dodo_python_pool", pool_size=settings.mysql_pool_size,
                host=settings.mysql_host, port=settings.mysql_port, database=settings.mysql_database,
                user=settings.mysql_user, password=settings.mysql_password, charset="utf8mb4",
            )
            self._init_mysql()
        elif self.backend == "sqlite":
            self.db_path = settings.db_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite()
        else:
            raise ValueError("DODO_STORAGE_BACKEND must be mysql or sqlite")

    def _connect_mysql(self):
        assert self._mysql_pool is not None
        connection = self._mysql_pool.get_connection()
        connection.autocommit = True
        return connection

    def _connect_sqlite(self):
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_mysql(self) -> None:
        connection = self._connect_mysql()
        try:
            cursor = connection.cursor()
            cursor.execute("""CREATE TABLE IF NOT EXISTS ai_file_info (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, file_id VARCHAR(255) NOT NULL UNIQUE,
                file_name VARCHAR(500) NOT NULL, file_type VARCHAR(50), file_size BIGINT,
                minio_path VARCHAR(1000), extracted_text LONGTEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                conversation_id VARCHAR(255), status VARCHAR(50) DEFAULT 'PENDING',
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, embed TINYINT DEFAULT 0,
                INDEX idx_file_conversation (conversation_id)) CHARACTER SET utf8mb4""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS ai_session (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, session_id VARCHAR(255) NOT NULL,
                question LONGTEXT, answer LONGTEXT, tools VARCHAR(1024), first_response_time BIGINT,
                total_response_time BIGINT, create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, reference LONGTEXT,
                agent_type VARCHAR(255), thinking LONGTEXT, fileid VARCHAR(255), recommend VARCHAR(1000),
                INDEX idx_session_id (session_id), INDEX idx_session_create (create_time)) CHARACTER SET utf8mb4""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS ai_ppt_inst (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, conversation_id VARCHAR(64), template_code VARCHAR(50),
                status VARCHAR(32), query TEXT, requirement LONGTEXT, search_info LONGTEXT, outline LONGTEXT,
                ppt_schema LONGTEXT, file_url VARCHAR(1000), error_msg TEXT, create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_ppt_conversation (conversation_id), INDEX idx_ppt_status (status)) CHARACTER SET utf8mb4""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS ai_ppt_template (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, template_code VARCHAR(50) NOT NULL UNIQUE,
                template_name VARCHAR(100) NOT NULL, template_desc TEXT, template_schema LONGTEXT NOT NULL,
                file_path VARCHAR(500) NOT NULL, style_tags VARCHAR(200), slide_count INT,
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP) CHARACTER SET utf8mb4""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS ai_document (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, doc_id VARCHAR(64) NOT NULL UNIQUE,
                file_name VARCHAR(500) NOT NULL, doc_type VARCHAR(50), status VARCHAR(50) DEFAULT 'PENDING',
                converted_via VARCHAR(50), markdown_path VARCHAR(1000), image_count INT DEFAULT 0,
                caption_count INT DEFAULT 0, char_count INT DEFAULT 0, error_msg TEXT, version INT DEFAULT 0,
                embed TINYINT DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_document_status (status)) CHARACTER SET utf8mb4""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS ai_document_version (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, doc_id VARCHAR(64) NOT NULL, version INT NOT NULL,
                markdown_url VARCHAR(1000), image_map LONGTEXT, note VARCHAR(500),
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE KEY uk_document_version (doc_id, version)) CHARACTER SET utf8mb4""")
            cursor.close()
        finally:
            connection.close()

    def _init_sqlite(self) -> None:
        with self._connect_sqlite() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS ai_file_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT NOT NULL UNIQUE, file_name TEXT NOT NULL,
                file_type TEXT, file_size INTEGER, minio_path TEXT, extracted_text TEXT, created_at TEXT,
                conversation_id TEXT, status TEXT DEFAULT 'PENDING', update_time TEXT, embed INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS ai_session (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, question TEXT, answer TEXT,
                tools TEXT, first_response_time INTEGER, total_response_time INTEGER, create_time TEXT, update_time TEXT,
                reference TEXT, agent_type TEXT, thinking TEXT, fileid TEXT, recommend TEXT);
                CREATE TABLE IF NOT EXISTS ai_ppt_inst (
                id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, template_code TEXT, status TEXT, query TEXT,
                requirement TEXT, search_info TEXT, outline TEXT, ppt_schema TEXT, file_url TEXT, error_msg TEXT,
                create_time TEXT, update_time TEXT);
                CREATE TABLE IF NOT EXISTS ai_ppt_template (
                id INTEGER PRIMARY KEY AUTOINCREMENT, template_code TEXT UNIQUE, template_name TEXT, template_desc TEXT,
                template_schema TEXT, file_path TEXT, style_tags TEXT, slide_count INTEGER, create_time TEXT);
                CREATE TABLE IF NOT EXISTS ai_document (
                id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL UNIQUE, file_name TEXT NOT NULL,
                doc_type TEXT, status TEXT DEFAULT 'PENDING', converted_via TEXT, markdown_path TEXT,
                image_count INTEGER DEFAULT 0, caption_count INTEGER DEFAULT 0, char_count INTEGER DEFAULT 0,
                error_msg TEXT, version INTEGER DEFAULT 0, embed INTEGER DEFAULT 0, created_at TEXT, update_time TEXT);
                CREATE TABLE IF NOT EXISTS ai_document_version (
                id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL, version INTEGER NOT NULL,
                markdown_url TEXT, image_map TEXT, note TEXT, create_time TEXT, UNIQUE (doc_id, version));""")

    def _file(self, row: Any) -> FileInfo:
        return FileInfo(fileId=row["file_id"], fileName=row["file_name"], fileType=row["file_type"],
                        fileSize=int(row["file_size"] or 0), minioPath=row["minio_path"], status=row["status"] or "PENDING",
                        extractedText=row["extracted_text"] or "", conversationId=row["conversation_id"],
                        embed=int(row["embed"] or 0), createdAt=str(row["created_at"] or ""))

    def _message(self, row: Any) -> SessionMessage:
        return SessionMessage(id=int(row["id"]), conversationId=row["session_id"], question=row["question"] or "",
                              answer=row["answer"], thinking=row["thinking"], tools=row["tools"], reference=row["reference"],
                              agentType=row["agent_type"] or "chat", fileid=row["fileid"], recommend=row["recommend"],
                              createTime=str(row["create_time"] or ""))

    def _execute(self, sql: str, params: tuple = (), fetch: str | None = None):
        if self.backend == "sqlite":
            with self._lock, self._connect_sqlite() as db:
                cursor = db.execute(sql, params)
                if fetch == "one": return cursor.fetchone()
                if fetch == "all": return cursor.fetchall()
                return cursor
        connection = self._connect_mysql()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(sql.replace("?", "%s"), params)
            if fetch == "one": return cursor.fetchone()
            if fetch == "all": return cursor.fetchall()
            return cursor.lastrowid
        finally:
            cursor.close(); connection.close()

    def save_file(self, info: FileInfo) -> None:
        values = (info.fileId, info.fileName, info.fileType, info.fileSize, info.minioPath, info.extractedText,
                  info.createdAt or now_iso(), info.conversationId, info.status, now_iso(), info.embed)
        if self.backend == "sqlite":
            self._execute("""INSERT INTO ai_file_info
                (file_id,file_name,file_type,file_size,minio_path,extracted_text,created_at,conversation_id,status,update_time,embed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(file_id) DO UPDATE SET file_name=excluded.file_name,
                file_type=excluded.file_type,file_size=excluded.file_size,minio_path=excluded.minio_path,
                extracted_text=excluded.extracted_text,conversation_id=excluded.conversation_id,status=excluded.status,
                update_time=excluded.update_time,embed=excluded.embed""", values)
        else:
            self._execute("""INSERT INTO ai_file_info
                (file_id,file_name,file_type,file_size,minio_path,extracted_text,created_at,conversation_id,status,update_time,embed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE file_name=VALUES(file_name),file_type=VALUES(file_type),
                file_size=VALUES(file_size),minio_path=VALUES(minio_path),extracted_text=VALUES(extracted_text),
                conversation_id=VALUES(conversation_id),status=VALUES(status),update_time=VALUES(update_time),embed=VALUES(embed)""", values)

    def get_file(self, file_id: str) -> FileInfo | None:
        row = self._execute("SELECT * FROM ai_file_info WHERE file_id = ?", (file_id,), "one")
        return self._file(row) if row else None

    def list_files(self) -> list[FileInfo]:
        return [self._file(row) for row in self._execute("SELECT * FROM ai_file_info ORDER BY created_at DESC", fetch="all")]

    def delete_file(self, file_id: str) -> bool:
        if self.backend == "sqlite":
            return self._execute("DELETE FROM ai_file_info WHERE file_id = ?", (file_id,)).rowcount > 0
        connection = self._connect_mysql()
        try:
            cursor = connection.cursor(); cursor.execute("DELETE FROM ai_file_info WHERE file_id = %s", (file_id,)); return cursor.rowcount > 0
        finally:
            cursor.close(); connection.close()

    def save_question(self, conversation_id: str, question: str, agent_type: str, file_id: str | None) -> int:
        now = now_iso(); values = (conversation_id, question, agent_type, file_id, now, now)
        return int(self._execute("INSERT INTO ai_session(session_id,question,agent_type,fileid,create_time,update_time) VALUES (?,?,?,?,?,?)", values)) if self.backend == "mysql" else int(self._execute("INSERT INTO ai_session(session_id,question,agent_type,fileid,create_time,update_time) VALUES (?,?,?,?,?,?)", values).lastrowid)

    def update_answer(self, row_id: int, answer: str, thinking: str = "", tools: str = "", reference: Any = None, recommend: Any = None) -> None:
        ref = json.dumps(reference, ensure_ascii=False) if not isinstance(reference, str) and reference is not None else reference
        rec = json.dumps(recommend, ensure_ascii=False) if not isinstance(recommend, str) and recommend is not None else recommend
        self._execute("UPDATE ai_session SET answer=?,thinking=?,tools=?,reference=?,recommend=?,update_time=? WHERE id=?", (answer, thinking, tools, ref, rec, now_iso(), row_id))

    def session_messages(self, conversation_id: str) -> list[SessionMessage]:
        return [self._message(row) for row in self._execute("SELECT * FROM ai_session WHERE session_id=? ORDER BY id ASC", (conversation_id,), "all")]

    def conversation_file_id(self, conversation_id: str) -> str | None:
        row = self._execute(
            "SELECT fileid FROM ai_session WHERE session_id=? AND fileid IS NOT NULL ORDER BY id DESC LIMIT 1",
            (conversation_id,), "one")
        return row["fileid"] if row else None

    def session_list(self, offset: int, limit: int) -> tuple[list[SessionMessage], int]:
        count = self._execute("SELECT COUNT(DISTINCT session_id) AS total FROM ai_session", fetch="one")["total"]
        rows = self._execute("""SELECT s.* FROM ai_session s JOIN (SELECT session_id, MIN(id) id FROM ai_session GROUP BY session_id) first ON first.id=s.id
            ORDER BY s.update_time DESC, s.id DESC LIMIT ? OFFSET ?""", (limit, offset), "all")
        return [self._message(row) for row in rows], int(count)

    def delete_session(self, conversation_id: str) -> bool:
        existed = bool(self.session_messages(conversation_id))
        self._execute("DELETE FROM ai_file_info WHERE conversation_id=?", (conversation_id,)); self._execute("DELETE FROM ai_ppt_inst WHERE conversation_id=?", (conversation_id,)); self._execute("DELETE FROM ai_session WHERE session_id=?", (conversation_id,))
        return existed

    def _document(self, row: Any) -> DocumentRecord:
        return DocumentRecord(fileId=row["doc_id"], fileName=row["file_name"], docType=row["doc_type"] or "",
                              status=row["status"] or "PENDING", convertedVia=row["converted_via"] or "",
                              markdownUrl=row["markdown_path"] or "", imageCount=int(row["image_count"] or 0),
                              captionCount=int(row["caption_count"] or 0), charCount=int(row["char_count"] or 0),
                              errorMsg=row["error_msg"] or "", version=int(row["version"] or 0),
                              embed=int(row["embed"] or 0), createdAt=str(row["created_at"] or ""))

    def save_document(self, doc: DocumentRecord) -> None:
        values = (doc.fileId, doc.fileName, doc.docType, doc.status, doc.convertedVia, doc.markdownUrl,
                  doc.imageCount, doc.captionCount, doc.charCount, doc.errorMsg, doc.version, doc.embed,
                  doc.createdAt or now_iso(), now_iso())
        columns = "doc_id,file_name,doc_type,status,converted_via,markdown_path,image_count,caption_count,char_count,error_msg,version,embed,created_at,update_time"
        if self.backend == "sqlite":
            self._execute(f"INSERT INTO ai_document ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                          "ON CONFLICT(doc_id) DO UPDATE SET file_name=excluded.file_name,doc_type=excluded.doc_type,"
                          "status=excluded.status,converted_via=excluded.converted_via,markdown_path=excluded.markdown_path,"
                          "image_count=excluded.image_count,caption_count=excluded.caption_count,"
                          "char_count=excluded.char_count,error_msg=excluded.error_msg,version=excluded.version,"
                          "embed=excluded.embed,update_time=excluded.update_time", values)
        else:
            self._execute(f"INSERT INTO ai_document ({columns}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                          "ON DUPLICATE KEY UPDATE file_name=VALUES(file_name),doc_type=VALUES(doc_type),"
                          "status=VALUES(status),converted_via=VALUES(converted_via),markdown_path=VALUES(markdown_path),"
                          "image_count=VALUES(image_count),caption_count=VALUES(caption_count),"
                          "char_count=VALUES(char_count),error_msg=VALUES(error_msg),version=VALUES(version),"
                          "embed=VALUES(embed),update_time=VALUES(update_time)", values)

    def get_document(self, doc_id: str) -> DocumentRecord | None:
        row = self._execute("SELECT * FROM ai_document WHERE doc_id = ?", (doc_id,), "one")
        return self._document(row) if row else None

    def list_documents(self) -> list[DocumentRecord]:
        return [self._document(row) for row in
                self._execute("SELECT * FROM ai_document ORDER BY created_at DESC", fetch="all")]

    def documents_by_status(self, statuses: tuple[str, ...], limit: int = 20) -> list[DocumentRecord]:
        marks = ",".join("?" for _ in statuses)
        return [self._document(row) for row in self._execute(
            f"SELECT * FROM ai_document WHERE status IN ({marks}) ORDER BY created_at ASC LIMIT ?",
            (*statuses, limit), "all")]

    def delete_document(self, doc_id: str) -> None:
        self._execute("DELETE FROM ai_document_version WHERE doc_id=?", (doc_id,))
        self._execute("DELETE FROM ai_document WHERE doc_id=?", (doc_id,))

    def add_document_version(self, doc_id: str, version: int, url: str, image_map: dict[str, str], note: str = "") -> None:
        self._execute("""INSERT INTO ai_document_version (doc_id, version, markdown_url, image_map, note, create_time)
            VALUES (?,?,?,?,?,?) ON CONFLICT(doc_id, version) DO UPDATE SET markdown_url=excluded.markdown_url,
            image_map=excluded.image_map, note=excluded.note""" if self.backend == "sqlite" else
            """INSERT INTO ai_document_version (doc_id, version, markdown_url, image_map, note, create_time)
            VALUES (?,?,?,?,?,?) ON DUPLICATE KEY UPDATE markdown_url=VALUES(markdown_url),
            image_map=VALUES(image_map), note=VALUES(note)""",
            (doc_id, version, url, json.dumps(image_map, ensure_ascii=False), note, now_iso()))

    def list_document_versions(self, doc_id: str) -> list[dict[str, Any]]:
        rows = self._execute("SELECT * FROM ai_document_version WHERE doc_id=? ORDER BY version DESC", (doc_id,), "all")
        return [{"version": int(row["version"]), "markdownUrl": row["markdown_url"],
                 "imageMap": json.loads(row["image_map"] or "{}"), "note": row["note"],
                 "createTime": str(row["create_time"] or "")} for row in rows]
