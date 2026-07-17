from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from types import TracebackType

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


class JobAlreadyRunningError(RuntimeError):
    pass


class JobLock:
    """PostgreSQL advisory lock, with a host-local file lock for other databases."""

    def __init__(self, job_name: str, engine: Engine, lock_dir: str | None = None) -> None:
        self.job_name = job_name
        self.engine = engine
        self.lock_dir = Path(lock_dir or tempfile.gettempdir()) / "kanggaemi-batch-locks"
        self._connection: Connection | None = None
        self._file = None

    def __enter__(self) -> "JobLock":
        if self.engine.dialect.name == "postgresql":
            self._acquire_postgresql()
        else:
            self._acquire_file()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._connection is not None:
            try:
                self._connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self._lock_key})
            finally:
                self._connection.close()
                self._connection = None
        if self._file is not None:
            self._unlock_file()

    @property
    def _lock_key(self) -> int:
        raw = hashlib.sha256(f"kanggaemi:{self.job_name}".encode()).digest()[:8]
        return int.from_bytes(raw, byteorder="big", signed=True)

    def _acquire_postgresql(self) -> None:
        connection = self.engine.connect()
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": self._lock_key}
        ).scalar()
        if not acquired:
            connection.close()
            raise JobAlreadyRunningError(f"job already running: {self.job_name}")
        self._connection = connection

    def _acquire_file(self) -> None:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        path = self.lock_dir / f"{self.job_name}.lock"
        file = None
        try:
            file = path.open("a+b")
            file.seek(0)
            if file.read(1) == b"":
                file.write(b"0")
                file.flush()
            if os.name == "nt":
                import msvcrt

                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if file is not None:
                file.close()
            raise JobAlreadyRunningError(f"job already running: {self.job_name}") from exc
        self._file = file

    def _unlock_file(self) -> None:
        file = self._file
        self._file = None
        try:
            if os.name == "nt":
                import msvcrt

                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(file.fileno(), fcntl.LOCK_UN)
        finally:
            file.close()
