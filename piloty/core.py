"""Quiescence-based PTY management.

PTY has two states:
- busy: producing output
- quiescent: silent for N ms (default 500ms)

State interpretation is performed outside this module (heuristics or MCP sampling).
"""

from __future__ import annotations

import inspect
import json
import os
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import pexpect
import pyte


class _PyteListenerProxy:
    """Adapter to tolerate pyte sending keyword args (e.g., private=True).

    pyte.Stream dispatches some CSI handlers with a 'private' kwarg. pyte.Screen
    methods vary in whether they accept it. This proxy forwards 'private' only
    when the target method supports it.
    """

    def __init__(self, screen: pyte.Screen):
        self._screen = screen

    def __getattr__(self, name: str):
        target = getattr(self._screen, name)
        if not callable(target):
            return target

        try:
            sig = inspect.signature(target)
            supports_private = "private" in sig.parameters
        except Exception:
            supports_private = False

        def wrapper(*args, private: bool = False, **_kwargs):
            if supports_private:
                return target(*args, private=private)
            return target(*args)

        return wrapper


class PTY:
    """Quiescence-based PTY wrapper with best-effort VT100 rendering."""

    def __init__(
        self,
        session_id: str = "default",
        rows: int = 24,
        cols: int = 80,
        log_dir: str | None = None,
    ):
        self.session_id = session_id
        self.rows = rows
        self.cols = cols
        self._lock = threading.Lock()

        self._max_lines = 100
        self._context_lines = 20

        if log_dir is None:
            base = Path.home() / ".piloty" / "sessions"
            safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id).strip("._-")
            if not safe:
                safe = "default"
            log_dir = str(base / safe)
        self._safe_id = Path(log_dir).name
        self._session_dir = Path(log_dir)
        os.makedirs(log_dir, exist_ok=True)
        self._transcript_path = os.path.join(log_dir, "transcript.log")
        self._transcript_file = open(self._transcript_path, "a", encoding="utf-8")
        self._commands_path = str(self._session_dir / "commands.log")
        self._interaction_path = str(self._session_dir / "interaction.log")
        self._state_path = str(self._session_dir / "state.json")
        self._session_meta_path = str(self._session_dir / "session.json")

        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(_PyteListenerProxy(self._screen))
        self._vt100_ok = True
        self._vt100_error: str | None = None

        self._capture_reset()
        self._last_output_preview = ""
        self._fatal_error: str | None = None
        self._last_output_time = time.monotonic()

        env = {
            **os.environ,
            "TERM": "xterm-256color",
            "LINES": str(rows),
            "COLUMNS": str(cols),
        }

        self._process = pexpect.spawn(
            "bash",
            ["--norc", "--noprofile"],
            encoding="utf-8",
            codec_errors="replace",
            echo=False,
            env=env,
            dimensions=(rows, cols),
        )

        self._drain(quiescence_ms=500, timeout=2.0, log=True, capture=False)
        self._write_session_meta()
        self._ensure_active_symlink()
        self._write_state()

    def type(self, text: str, timeout: float = 30.0, quiescence_ms: int = 500, log: bool = True) -> dict:
        with self._lock:
            if not self.alive:
                return {"status": "eof", "output": "", "error": "pty not alive"}

            self._fatal_error = None
            self._capture_reset()

            try:
                self._process.send(text)
            except Exception as e:
                self._fatal_error = f"{type(e).__name__}: {e}"
                return {"status": "error", "output": "", "error": self._fatal_error}
            self._last_output_time = time.monotonic()

            status = self._drain(quiescence_ms=quiescence_ms, timeout=timeout, log=log, capture=True)
            output = self._capture_output()
            self._last_output_preview = output
            if log:
                self._append_command(text)
                self._append_interaction(text, output, status)
                self._write_state()

            resp = {"status": status, "output": output}
            if status == "error" and self._fatal_error:
                resp["error"] = self._fatal_error
            return resp

    def poll_output(self, timeout: float = 0.1, quiescence_ms: int = 100, log: bool = True) -> dict:
        """Drain pending output without sending input."""
        with self._lock:
            self._fatal_error = None
            self._capture_reset()
            status = self._drain(quiescence_ms=quiescence_ms, timeout=timeout, log=log, capture=True)
            output = self._capture_output()
            self._last_output_preview = output
            resp = {"status": status, "output": output}
            if status == "error" and self._fatal_error:
                resp["error"] = self._fatal_error
            return resp

    def read(self, log: bool = True) -> str:
        with self._lock:
            self._drain(quiescence_ms=100, timeout=0.5, log=log, capture=False)

            if not self._vt100_ok:
                return self._last_output_preview

            lines: list[str] = []
            for line in self._screen.display:
                stripped = line.rstrip()
                if stripped or lines:
                    lines.append(stripped)

            while lines and not lines[-1]:
                lines.pop()

            return "\n".join(lines)

    def transcript(self) -> str:
        return self._transcript_path

    def terminate(self):
        with self._lock:
            if self._process.isalive():
                self._process.terminate(force=True)
            try:
                self._transcript_file.close()
            except Exception:
                pass
            self._write_session_meta(end_time=self._now_iso())
            self._remove_active_symlink()

    @property
    def alive(self) -> bool:
        return self._process.isalive()

    def _drain(self, quiescence_ms: int = 500, timeout: float = 30.0, log: bool = True, capture: bool = True) -> str:
        deadline = time.monotonic() + timeout
        quiescence_s = quiescence_ms / 1000.0

        while True:
            now = time.monotonic()
            if now >= deadline:
                return "timeout"

            silence = now - self._last_output_time
            if silence >= quiescence_s:
                return "quiescent"

            time_until_quiescent = quiescence_s - silence
            time_until_deadline = deadline - now
            read_timeout = min(time_until_quiescent, time_until_deadline, 0.1)

            try:
                chunk = self._process.read_nonblocking(size=4096, timeout=read_timeout)
                if chunk:
                    self._last_output_time = time.monotonic()
                    if capture:
                        self._capture_chunk(chunk)
                    if self._vt100_ok:
                        try:
                            self._stream.feed(chunk)
                        except Exception as e:
                            self._vt100_ok = False
                            self._vt100_error = f"{type(e).__name__}: {e}"
                    if log:
                        try:
                            self._transcript_file.write(chunk)
                            self._transcript_file.flush()
                        except Exception:
                            pass
            except pexpect.TIMEOUT:
                pass
            except pexpect.EOF:
                return "eof"
            except Exception as e:
                self._fatal_error = f"{type(e).__name__}: {e}"
                return "error"

    def _capture_reset(self):
        self._full_lines: list[str] | None = []
        self._head_lines: list[str] = []
        self._tail_lines: deque[str] = deque(maxlen=self._context_lines)
        self._total_lines: int = 0
        self._line_buf: str = ""

    def _capture_chunk(self, chunk: str):
        self._line_buf += chunk
        parts = self._line_buf.splitlines(True)
        if parts and not parts[-1].endswith(("\n", "\r")):
            self._line_buf = parts.pop()
        else:
            self._line_buf = ""
        for line in parts:
            self._capture_line(line)

    def _capture_line(self, line: str):
        self._total_lines += 1
        if self._full_lines is not None:
            self._full_lines.append(line)
            if len(self._full_lines) > self._max_lines:
                full = self._full_lines
                self._full_lines = None
                self._head_lines = full[: self._context_lines]
                self._tail_lines = deque(full[-self._context_lines :], maxlen=self._context_lines)
        else:
            self._tail_lines.append(line)

    def _capture_output(self) -> str:
        if self._line_buf:
            self._capture_line(self._line_buf)
            self._line_buf = ""

        if self._full_lines is not None:
            return "".join(self._full_lines)

        head = self._head_lines
        tail = list(self._tail_lines)
        elided = self._total_lines - len(head) - len(tail)
        if elided < 0:
            elided = 0
        return "".join(head) + f"\n\n... [{elided} lines elided, see transcript] ...\n\n" + "".join(tail)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _write_json(self, path: str, obj: dict):
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, sort_keys=True)
        os.replace(tmp, path)

    def _write_session_meta(self, end_time: str | None = None):
        meta = {
            "session_id": self.session_id,
            "safe_id": self._safe_id,
            "start_time": self._now_iso(),
            "end_time": end_time,
            "pid": getattr(self._process, "pid", None),
            "initial_cwd": os.getcwd(),
            "rows": self.rows,
            "cols": self.cols,
        }
        if os.path.exists(self._session_meta_path):
            try:
                existing = json.loads(Path(self._session_meta_path).read_text(encoding="utf-8"))
                meta["start_time"] = existing.get("start_time", meta["start_time"])
                meta["initial_cwd"] = existing.get("initial_cwd", meta["initial_cwd"])
            except Exception:
                pass
        if end_time is None:
            meta.pop("end_time")
        self._write_json(self._session_meta_path, meta)

    def _write_state(self):
        state = {
            "current_directory": None,
            "active_handler": None,
            "handler_context": None,
            "background_jobs": None,
            "vt100_ok": self._vt100_ok,
            "vt100_error": self._vt100_error,
            "transcript": self._transcript_path,
        }
        self._write_json(self._state_path, state)

    def _append_command(self, text: str):
        ts = self._now_iso()
        line = f"[{ts}] {text!r}\n"
        try:
            with open(self._commands_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def _append_interaction(self, text: str, output: str, status: str):
        ts = self._now_iso()
        try:
            with open(self._interaction_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] status={status} input={text!r}\n")
                f.write(output)
                if not output.endswith("\n"):
                    f.write("\n")
                f.write("\n")
        except Exception:
            pass

    def _ensure_active_symlink(self):
        active_dir = Path.home() / ".piloty" / "active"
        try:
            active_dir.mkdir(parents=True, exist_ok=True)
            link = active_dir / self._safe_id
            if link.exists() or link.is_symlink():
                link.unlink()
            os.symlink(str(self._session_dir), str(link))
        except Exception:
            pass

    def _remove_active_symlink(self):
        active_dir = Path.home() / ".piloty" / "active"
        link = active_dir / self._safe_id
        try:
            if link.is_symlink() or link.exists():
                link.unlink()
        except Exception:
            pass
