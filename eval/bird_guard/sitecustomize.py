"""BIRD subprocesses open SQLite databases read-only, including spawned workers."""
import sqlite3
from pathlib import Path

_connect = sqlite3.connect
_allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE}


def connect(database, *args, **kwargs):
    path = Path(database).resolve()
    kwargs['uri'] = True
    connection = _connect(path.as_uri() + '?mode=ro', *args, **kwargs)
    connection.enable_load_extension(False)
    connection.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in _allowed else sqlite3.SQLITE_DENY)
    return connection


sqlite3.connect = connect
