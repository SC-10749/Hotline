"""SQLite 存储的公共基类：连接、事务与补列。

仓库里十几个 store 都用 SQLite，各写一遍连接、事务与补列逻辑，改一处漏三处。
这里把三件事收在一处：

- ``_db()``：一个自动关闭的连接上下文。
- ``_transaction()``：``BEGIN IMMEDIATE`` 事务，异常回滚并**重新抛出**。
- ``ensure_columns()``：给已有表补列，幂等。

各 store 之间的真实差异（超时、isolation_level、是否开外键）用类属性表达，
不靠复制代码表达。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


class SqliteStore:
    """SQLite 持久化基类。子类实现 _initialize() 建表。"""

    # 多数 store 用 30 秒等待写锁；短超时的 store 覆盖这个类属性。
    timeout = 30
    # None 表示 autocommit，事务边界由 _transaction() 显式给出。
    isolation_level: str | None = None
    # 是否开启外键约束；执行队列的表有外键，需要打开。
    foreign_keys = False

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=self.isolation_level)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout = 30000')
        if self.foreign_keys:
            db.execute('PRAGMA foreign_keys = ON')
        return db

    @contextmanager
    def _db(self):
        db = self._connect()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self):
        """写事务：正常结束提交，异常回滚并原样抛出。"""
        db = self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def ensure_columns(db: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        """给已有表补列；已存在的列不动，重复调用安全。"""
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def _initialize(self) -> None:
        """子类在这里建表。"""
        raise NotImplementedError
