"""Token storage backends.

Every backend stores a single :class:`~bling_api_v3_auth.models.TokenData` bundle
(one Bling account). Implement :class:`TokenStorage` to plug in your own backend
(database, secret manager...).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bling_api_v3_auth.exceptions import AuthorizationRequiredError, BlingConfigError
from bling_api_v3_auth.models import TokenData

if TYPE_CHECKING:
    from collections.abc import Iterator

DEFAULT_TOKEN_FILE = Path.home() / ".config" / "bling_api_v3_auth" / "credentials.json"
DEFAULT_REDIS_KEY = "bling_api_v3_auth:token"


class TokenStorage(ABC):
    """Interface for token persistence."""

    @abstractmethod
    def load(self) -> TokenData | None:
        """Return the stored tokens, or ``None`` if nothing is stored."""

    @abstractmethod
    def save(self, token: TokenData) -> None:
        """Persist ``token``, replacing any previously stored value."""

    @abstractmethod
    def clear(self) -> None:
        """Remove the stored tokens."""

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        """Context manager that serializes token refreshes.

        Bling rotates the refresh token on every use, so two concurrent refreshes
        would invalidate each other. The default implementation is a no-op; the
        :class:`~bling_api_v3_auth.manager.BlingAuthManager` already serializes
        refreshes inside a process. Backends shared between processes (e.g. Redis)
        override this with a distributed lock.
        """
        yield


class MemoryTokenStorage(TokenStorage):
    """In-memory storage. Useful for tests and short-lived scripts."""

    def __init__(self, token: TokenData | None = None) -> None:
        self._token = token
        self._lock = threading.Lock()

    def load(self) -> TokenData | None:  # noqa: D102
        with self._lock:
            return self._token

    def save(self, token: TokenData) -> None:  # noqa: D102
        with self._lock:
            self._token = token

    def clear(self) -> None:  # noqa: D102
        with self._lock:
            self._token = None


class JsonTokenStorage(TokenStorage):
    """Stores tokens in a local JSON file with owner-only permissions (``0600``).

    Writes are atomic (temporary file + ``os.replace``), so a crash in the middle of
    a write never leaves a truncated credentials file behind.
    Loading malformed JSON raises ``AuthorizationRequiredError`` with instructions
    to authorize again; the existing file is preserved.

    Args:
        path: File location. Defaults to ``~/.config/bling_api_v3_auth/credentials.json``.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else DEFAULT_TOKEN_FILE

    def load(self) -> TokenData | None:  # noqa: D102
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        if not raw.strip():
            return None
        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = f"Invalid token JSON in {self.path}. Authorize again with: bling-auth login"
            raise AuthorizationRequiredError(msg) from exc
        if not isinstance(data, dict):
            return None
        return TokenData.from_dict(data)

    def save(self, token: TokenData) -> None:  # noqa: D102
        directory = self.path.parent
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".credentials-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(token.to_dict(), file, indent=2)
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self.path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_name)
            raise

    def clear(self) -> None:  # noqa: D102
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()


class RedisTokenStorage(TokenStorage):
    """Stores tokens in Redis as a JSON document. Requires ``pip install bling-api-v3-auth[redis]``.

    The key expires together with the refresh token, and :meth:`lock` uses a Redis
    lock so several processes/hosts can share the same Bling credentials safely.

    Args:
        client: An existing ``redis.Redis`` client. If omitted, one is built from ``url``.
        url: Redis URL (e.g. ``redis://:password@localhost:6379/0``).
        key: Key used to store the tokens.
        lock_timeout: Seconds after which a stale refresh lock is released.
    """

    def __init__(
        self,
        client: Any = None,
        *,
        url: str | None = None,
        key: str = DEFAULT_REDIS_KEY,
        lock_timeout: float = 30.0,
    ) -> None:
        if client is None:
            try:
                import redis  # noqa: PLC0415
            except ModuleNotFoundError as exc:
                msg = (
                    "Redis support is not installed. "
                    "Install it with: pip install 'bling-api-v3-auth[redis]'"
                )
                raise BlingConfigError(msg) from exc
            client = redis.Redis.from_url(url or "redis://localhost:6379/0")
        self.client = client
        self.key = key
        self.lock_timeout = lock_timeout

    def load(self) -> TokenData | None:  # noqa: D102
        raw = self.client.get(self.key)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data: Any = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return TokenData.from_dict(data)

    def save(self, token: TokenData) -> None:  # noqa: D102
        ttl = max(int(token.refresh_token_expires_at - time.time()), 1)
        self.client.set(self.key, json.dumps(token.to_dict()), ex=ttl)

    def clear(self) -> None:  # noqa: D102
        self.client.delete(self.key)

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:  # noqa: D102
        with self.client.lock(
            f"{self.key}:lock",
            timeout=self.lock_timeout,
            blocking_timeout=self.lock_timeout,
        ):
            yield
