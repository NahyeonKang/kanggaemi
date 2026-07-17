from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import BinaryIO, Callable


logger = logging.getLogger(__name__)


class KisTokenThrottle:
    """Host-local, cross-process reservation gate for KIS token issuance."""

    def __init__(self, state_dir: str | None = None) -> None:
        root = Path(
            state_dir
            or os.getenv("BATCH_KIS_TOKEN_STATE_DIR")
            or os.getenv("BATCH_LOCK_DIR")
            or tempfile.gettempdir()
        )
        self.state_dir = root / "kanggaemi-batch-locks"
        self.state_path = self.state_dir / "kis-token-issued-at.state"

    def reserve(
        self,
        job_name: str,
        min_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> float:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("a+b") as state:
            self._ensure_lockable_byte(state)
            self._lock(state)
            try:
                last_reserved_at = self._read_timestamp(state)
                wait_seconds = max(
                    0.0, last_reserved_at + min_interval_seconds - clock()
                )
                if wait_seconds > 0:
                    logger.info(
                        "kis_token_throttle_wait",
                        extra={
                            "event": "kis_token_throttle_wait",
                            "job": job_name,
                            "wait_seconds": round(wait_seconds, 3),
                            "min_interval_seconds": min_interval_seconds,
                        },
                    )
                    sleep(wait_seconds)
                reserved_at = clock()
                self._write_timestamp(state, reserved_at)
                logger.info(
                    "kis_token_slot_reserved",
                    extra={
                        "event": "kis_token_slot_reserved",
                        "job": job_name,
                        "reserved_at_epoch": reserved_at,
                    },
                )
                return wait_seconds
            finally:
                self._unlock(state)

    @staticmethod
    def _ensure_lockable_byte(state: BinaryIO) -> None:
        state.seek(0, os.SEEK_END)
        if state.tell() == 0:
            state.write(b"0")
            state.flush()

    @staticmethod
    def _read_timestamp(state: BinaryIO) -> float:
        state.seek(0)
        raw = state.read().decode("ascii", errors="ignore").strip()
        try:
            return float(raw)
        except ValueError:
            return 0.0

    @staticmethod
    def _write_timestamp(state: BinaryIO, value: float) -> None:
        state.seek(0)
        state.truncate()
        state.write(f"{value:.6f}".encode("ascii"))
        state.flush()
        os.fsync(state.fileno())

    @staticmethod
    def _lock(state: BinaryIO) -> None:
        state.seek(0)
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(state.fileno(), msvcrt.LK_NBLCK, 1)
                    return
                except OSError:
                    time.sleep(0.1)
        else:
            import fcntl

            fcntl.flock(state.fileno(), fcntl.LOCK_EX)

    @staticmethod
    def _unlock(state: BinaryIO) -> None:
        state.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(state.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(state.fileno(), fcntl.LOCK_UN)
