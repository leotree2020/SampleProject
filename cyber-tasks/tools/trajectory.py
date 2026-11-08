"""
Trajectory recorder for security-agent task attempts.

A trajectory is an append-only JSONL file: one JSON object per line, in the
order events happened. It captures the full process of an attempt -- not just
the final patch -- because the process (exploration, failed tries, tool calls,
verifier result, human review) is the part that is hard to synthesize and is
the asset described in ../../docs/cyber-specialized-ai-agent.md.

The format is intentionally simple and stable (see SCHEMA.md). This module has
no third-party dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class TrajectoryRecorder:
    """Append-only writer for a single attempt's trajectory."""

    def __init__(self, path: str, task_id: str, model: str,
                 task_metadata_path: str | None = None,
                 extra: dict[str, Any] | None = None):
        self.path = path
        self.run_id = uuid.uuid4().hex[:16]
        self._seq = 0
        self._t0 = time.monotonic()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        # truncate/start fresh
        self._fh = open(path, "w", encoding="utf-8")

        meta_digest = None
        if task_metadata_path and os.path.exists(task_metadata_path):
            meta_digest = sha256_file(task_metadata_path)

        self._write({
            "type": "run_meta",
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "task_id": task_id,
            "model": model,
            "created_at": _now_iso(),
            "task_metadata_sha256": meta_digest,
            "extra": extra or {},
        })

    # -- low level -------------------------------------------------------------
    def _write(self, obj: dict[str, Any]) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._fh.flush()

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    # -- events ----------------------------------------------------------------
    def step(self, phase: str, action: str, *, tool: str | None = None,
             tool_input: Any = None, tool_output_summary: str | None = None,
             status: str = "ok", note: str | None = None) -> None:
        """One unit of work: a tool call, a decision, an observation.

        phase:  'explore' | 'patch' | 'verify'
        status: 'ok' | 'fail' | 'error'
        """
        self._write({
            "type": "step",
            "seq": self._next_seq(),
            "ts": _now_iso(),
            "phase": phase,
            "action": action,
            "tool": tool,
            "tool_input": tool_input,
            "tool_output_summary": tool_output_summary,
            "status": status,
            "note": note,
        })

    def patch(self, *, target: str, diff: str, origin: str) -> None:
        """The candidate change. origin e.g. 'model' | 'oracle' | 'file'."""
        self._write({
            "type": "patch",
            "seq": self._next_seq(),
            "ts": _now_iso(),
            "target": target,
            "origin": origin,
            "diff": diff,
        })

    def score(self, *, result: str, criteria: dict[str, bool],
              exit_code: int | None = None, note: str | None = None) -> None:
        """Verifier outcome. result: 'SOLVED' | 'UNSOLVED'."""
        self._write({
            "type": "score",
            "seq": self._next_seq(),
            "ts": _now_iso(),
            "result": result,
            "criteria": criteria,
            "exit_code": exit_code,
            "note": note,
        })

    def human_review(self, *, reviewer: str, verdict: str,
                     notes: str | None = None) -> None:
        """Placeholder for a later human-in-the-loop pass.

        verdict e.g. 'confirmed' | 'rejected' | 'needs_work'.
        """
        self._write({
            "type": "human_review",
            "seq": self._next_seq(),
            "ts": _now_iso(),
            "reviewer": reviewer,
            "verdict": verdict,
            "notes": notes,
        })

    def end(self, *, result: str) -> None:
        self._write({
            "type": "run_end",
            "seq": self._next_seq(),
            "ts": _now_iso(),
            "result": result,
            "duration_s": round(time.monotonic() - self._t0, 3),
        })
        self._fh.close()

    # -- context manager -------------------------------------------------------
    def __enter__(self) -> "TrajectoryRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._fh.closed:
            if exc_type is not None:
                self._write({
                    "type": "run_end",
                    "seq": self._next_seq(),
                    "ts": _now_iso(),
                    "result": "ERROR",
                    "error": repr(exc),
                    "duration_s": round(time.monotonic() - self._t0, 3),
                })
            self._fh.close()
