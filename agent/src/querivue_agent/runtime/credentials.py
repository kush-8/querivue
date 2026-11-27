"""Ollama Cloud credential pool management."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CredentialEntry:
    """Entry for a single credential in the pool."""
    credential_id: str
    api_key: str
    priority: int
    quota_group: str
    enabled: bool = True
    # Health state
    last_error_time: float = 0.0
    consecutive_errors: int = 0
    cooldown_until: float = 0.0


class OllamaCredentialPool:
    """Thread-safe credential pool for Ollama Cloud with priority selection and cooldowns."""

    def __init__(self, credentials: list[CredentialEntry]) -> None:
        if not credentials:
            raise ValueError("At least one credential must be provided")
        self._credentials = credentials
        self._lock = asyncio.Lock()
        # Group-level cooldown tracking
        self._group_cooldowns: dict[str, float] = {}

    def _select_healthy(self) -> CredentialEntry | None:
        """Select the highest-priority healthy credential."""
        now = time.time()
        healthy = [
            c for c in self._credentials
            if c.enabled
            and now >= c.cooldown_until
            and now >= self._group_cooldowns.get(c.quota_group, 0)
        ]
        if not healthy:
            return None
        # Sort by priority (lower number = higher priority)
        healthy.sort(key=lambda c: c.priority)
        return healthy[0]

    async def acquire(self) -> tuple[str, str]:
        """
        Acquire the best available credential.
        Returns (credential_id, api_key).
        Raises RuntimeError if no credentials available.
        """
        async with self._lock:
            entry = self._select_healthy()
            if entry is None:
                # Build error message with details
                now = time.time()
                details = []
                for c in self._credentials:
                    if not c.enabled:
                        details.append(f"{c.credential_id}: disabled")
                    elif now < c.cooldown_until:
                        details.append(f"{c.credential_id}: key cooldown until {c.cooldown_until:.0f}")
                    elif now < self._group_cooldowns.get(c.quota_group, 0):
                        details.append(f"{c.credential_id}: group {c.quota_group} cooldown")
                raise RuntimeError(f"No available Ollama Cloud credentials: {'; '.join(details)}")
            return entry.credential_id, entry.api_key

    def acquire_sync(self) -> tuple[str, str]:
        """
        Synchronously acquire the best available credential.
        Returns (credential_id, api_key).
        Raises RuntimeError if no credentials available.
        """
        import threading
        # Use threading lock for sync access
        if not hasattr(self, '_sync_lock'):
            self._sync_lock = threading.Lock()

        with self._sync_lock:
            entry = self._select_healthy()
            if entry is None:
                now = time.time()
                details = []
                for c in self._credentials:
                    if not c.enabled:
                        details.append(f"{c.credential_id}: disabled")
                    elif now < c.cooldown_until:
                        details.append(f"{c.credential_id}: key cooldown until {c.cooldown_until:.0f}")
                    elif now < self._group_cooldowns.get(c.quota_group, 0):
                        details.append(f"{c.credential_id}: group {c.quota_group} cooldown")
                raise RuntimeError(f"No available Ollama Cloud credentials: {'; '.join(details)}")
            return entry.credential_id, entry.api_key

    async def record_success(self, credential_id: str) -> None:
        """Record a successful request for the credential."""
        async with self._lock:
            for c in self._credentials:
                if c.credential_id == credential_id:
                    c.consecutive_errors = 0
                    c.last_error_time = 0.0
                    break

    async def record_error(
        self,
        credential_id: str,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Record an error for the credential and apply cooldowns."""
        async with self._lock:
            for c in self._credentials:
                if c.credential_id == credential_id:
                    c.consecutive_errors += 1
                    c.last_error_time = time.time()

                    # Key-specific cooldown for 429
                    if status_code == 429:
                        cooldown = retry_after or min(60.0 * (2 ** min(c.consecutive_errors, 5)), 300.0)
                        c.cooldown_until = time.time() + cooldown
                        # Also cool down the entire quota group
                        self._group_cooldowns[c.quota_group] = time.time() + cooldown
                    # Key-specific cooldown for 401/403 (auth issues)
                    elif status_code in (401, 403):
                        c.enabled = False
                        c.cooldown_until = time.time() + 3600  # 1 hour
                    # Generic error cooldown
                    elif status_code and 500 <= status_code < 600:
                        cooldown = min(10.0 * c.consecutive_errors, 60.0)
                        c.cooldown_until = time.time() + cooldown
                    break

    async def get_status(self) -> list[dict[str, Any]]:
        """Get status of all credentials."""
        async with self._lock:
            now = time.time()
            return [
                {
                    "credential_id": c.credential_id,
                    "priority": c.priority,
                    "quota_group": c.quota_group,
                    "enabled": c.enabled,
                    "healthy": c.enabled and now >= c.cooldown_until and now >= self._group_cooldowns.get(c.quota_group, 0),
                    "consecutive_errors": c.consecutive_errors,
                    "cooldown_remaining": max(0.0, c.cooldown_until - now),
                    "group_cooldown_remaining": max(0.0, self._group_cooldowns.get(c.quota_group, 0) - now),
                }
                for c in self._credentials
            ]

    async def rotate_key(self, old_credential_id: str, new_api_key: str) -> None:
        """Rotate a credential (e.g., after revocation)."""
        async with self._lock:
            for c in self._credentials:
                if c.credential_id == old_credential_id:
                    c.api_key = new_api_key
                    c.enabled = True
                    c.consecutive_errors = 0
                    c.cooldown_until = 0.0
                    c.last_error_time = 0.0
                    # Clear group cooldown for this key's group
                    if c.quota_group in self._group_cooldowns:
                        del self._group_cooldowns[c.quota_group]
                    break

    async def disable_credential(self, credential_id: str) -> None:
        """Manually disable a credential."""
        async with self._lock:
            for c in self._credentials:
                if c.credential_id == credential_id:
                    c.enabled = False
                    break

    async def enable_credential(self, credential_id: str) -> None:
        """Manually enable a credential."""
        async with self._lock:
            for c in self._credentials:
                if c.credential_id == credential_id:
                    c.enabled = True
                    c.cooldown_until = 0.0
                    break