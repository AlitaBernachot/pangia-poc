# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import get_session_factory

logger = logging.getLogger(__name__)

_ZERO_HASH = "0" * 64
_lock = asyncio.Lock()
_last_hash: dict[str, str] = {}  # per-session last hash


def _compute_hash(hash_prev: str, timestamp: str, event_type: str, data: dict) -> str:
    raw = hash_prev + timestamp + event_type + json.dumps(data, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


class AuditService:
    async def log(
        self,
        session_id: str,
        event_type: str,
        data: dict[str, Any],
        agent_name: str | None = None,
    ) -> None:
        asyncio.create_task(self._write(session_id, event_type, data, agent_name))

    async def _write(
        self,
        session_id: str,
        event_type: str,
        data: dict[str, Any],
        agent_name: str | None,
    ) -> None:
        try:
            async with _lock:
                hash_prev = _last_hash.get(session_id, _ZERO_HASH)
                ts = datetime.now(timezone.utc).isoformat()
                hash_current = _compute_hash(hash_prev, ts, event_type, data)
                _last_hash[session_id] = hash_current

            factory = get_session_factory()
            async with factory() as session:
                await session.execute(
                    text(
                        """
                        INSERT INTO audit_logs
                          (timestamp, session_id, event_type, agent_name, data, hash_prev, hash_current)
                        VALUES
                          (:ts, :session_id, :event_type, :agent_name, :data::jsonb, :hash_prev, :hash_current)
                        """
                    ),
                    {
                        "ts": ts,
                        "session_id": session_id,
                        "event_type": event_type,
                        "agent_name": agent_name,
                        "data": json.dumps(data),
                        "hash_prev": hash_prev,
                        "hash_current": hash_current,
                    },
                )
                await session.commit()
        except Exception:
            logger.exception("AuditService: failed to write event %s", event_type)


_audit: AuditService | None = None


def get_audit() -> AuditService:
    global _audit
    if _audit is None:
        _audit = AuditService()
    return _audit
