"""Parallel-safe directory locks with stale lock cleanup."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import shutil
import time
import uuid

from .paths import lock_root
from .schemas import atomic_write_json, iso_now, parse_iso, read_json, slugify


@dataclass
class DirectoryLock:
    name: str
    purpose: str
    root: Path | None = None
    stale_seconds: int = 3600
    wait_seconds: int = 30
    poll_seconds: float = 0.25
    token: str = field(default_factory=lambda: uuid.uuid4().hex)
    acquired: bool = False

    @property
    def path(self) -> Path:
        base = self.root or lock_root()
        return base / f"{slugify(self.name, fallback='lock', max_length=120)}.lock"

    def _owner_path(self) -> Path:
        return self.path / "owner.json"

    def _is_stale(self) -> bool:
        owner = read_json(self._owner_path(), default={})
        created_at = owner.get("created_at") if isinstance(owner, dict) else None
        created = parse_iso(created_at) if isinstance(created_at, str) else None
        if created is not None:
            age = time.time() - created.timestamp()
        else:
            try:
                age = time.time() - self.path.stat().st_mtime
            except FileNotFoundError:
                return False
        return age > self.stale_seconds

    def acquire(self) -> "DirectoryLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.wait_seconds
        while True:
            try:
                self.path.mkdir(exist_ok=False)
                atomic_write_json(
                    self._owner_path(),
                    {
                        "pid": os.getpid(),
                        "created_at": iso_now(),
                        "purpose": self.purpose,
                        "token": self.token,
                    },
                )
                self.acquired = True
                return self
            except FileExistsError:
                if self._is_stale():
                    try:
                        shutil.rmtree(self.path)
                    except FileNotFoundError:
                        pass
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"could not acquire lock {self.path}")
                time.sleep(self.poll_seconds)

    def release(self) -> None:
        if not self.acquired:
            return
        owner = read_json(self._owner_path(), default={})
        if isinstance(owner, dict) and owner.get("token") == self.token:
            shutil.rmtree(self.path, ignore_errors=True)
        self.acquired = False

    def __enter__(self) -> "DirectoryLock":
        return self.acquire()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.release()

