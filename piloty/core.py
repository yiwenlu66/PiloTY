"""Quiescence-based PTY management.

PTY has two states:
- busy: producing output
- quiescent: silent for N ms (default 1000ms via PILOTY_QUIESCENCE_MS)

State interpretation is performed outside this module (heuristics or MCP sampling).
"""

from __future__ import annotations

import inspect
import json
import os
import re
import sys
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


def _path_without_entry(path_value: str, entry: str) -> str:
    if not path_value:
        return ""
    normalized_entry = os.path.normcase(os.path.abspath(entry))
    kept: list[str] = []
    for part in path_value.split(os.pathsep):
        if not part:
            continue
        normalized_part = os.path.normcase(os.path.abspath(part))
        if normalized_part == normalized_entry:
            continue
        kept.append(part)
    return os.pathsep.join(kept)


def _session_env(rows: int, cols: int) -> dict[str, str]:
    env = dict(os.environ)
    leaked_virtual_env = env.pop("VIRTUAL_ENV", None)
    env.pop("VIRTUAL_ENV_PROMPT", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env.pop("__PYVENV_LAUNCHER__", None)

    leaked_bins: set[str] = set()
    if leaked_virtual_env:
        leaked_bins.add(os.path.abspath(os.path.join(leaked_virtual_env, "bin")))

    exe_bin = os.path.abspath(os.path.dirname(sys.executable))
    if (Path(exe_bin).parent / "pyvenv.cfg").exists():
        leaked_bins.add(exe_bin)

    path_value = env.get("PATH", "")
    for leaked_bin in leaked_bins:
        path_value = _path_without_entry(path_value, leaked_bin)
    env["PATH"] = path_value

    env["TERM"] = "xterm-256color"
    env["LINES"] = str(rows)
    env["COLUMNS"] = str(cols)
    return env


class PTY:
    """Quiescence-based PTY wrapper with best-effort VT100 rendering."""

    def __init__(
        self,
        session_id: str = "default",
        rows: int = 24,
        cols: int = 80,
        cwd: str | None = None,
        shell: str | None = None,
        shell_args: list[str] | None = None,
        shell_prompt_regex: str | None = None,
        description: str | None = None,
        log_dir: str | None = None,
    ):
        self.session_id = session_id
        self.rows = rows
        self.cols = cols
        # Default to a deterministic shell (no user rc) to avoid prompt frameworks
        # emitting periodic output that prevents quiescence detection.
        if shell is None:
            self.shell = "bash"
            self.shell_args = ["--noprofile", "--norc"]
        else:
            self.shell = shell
            self.shell_args = shell_args or []
        self.shell_prompt_regex = shell_prompt_regex
        self.description = description
        self._lock = threading.Lock()
        self._quiescence_ms = int(os.getenv("PILOTY_QUIESCENCE_MS", "1000"))

        self._max_lines = 100
        self._context_lines = 20
        self._initial_cwd = os.path.abspath(cwd) if cwd else os.getcwd()
        self._started_at = self._now_iso()
        self._last_activity_at = self._started_at

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

        self._history_lines = 5000
        self._screen = pyte.HistoryScreen(cols, rows, history=self._history_lines)
        self._stream = pyte.Stream(_PyteListenerProxy(self._screen))
        self._vt100_ok = True
        self._vt100_error: str | None = None

        self._capture_reset()
        self._last_output_preview = ""
        self._fatal_error: str | None = None
        self._last_output_time = time.monotonic()

        env = _session_env(rows=rows, cols=cols)

        self._process = pexpect.spawn(
            self.shell,
            self.shell_args,
            encoding="utf-8",
            codec_errors="replace",
            echo=True,
            env=env,
            cwd=cwd,
            dimensions=(rows, cols),
        )

        self._drain(quiescence_ms=self._quiescence_ms, timeout=2.0, log=True, capture=False)
        self._write_session_meta()
        self._ensure_active_symlink()
        self._write_state()

    def type(
        self,
        text: str,
        timeout: float = 30.0,
        quiescence_ms: int | None = None,
        log: bool = True,
        echo: bool | None = None,
    ) -> dict:
        with self._lock:
            if not self.alive:
                return {"status": "eof", "output": "", "error": "pty not alive"}

            self._fatal_error = None
            self._capture_reset()

            prev_echo: bool | None = None
            changed_echo = False
            try:
                if echo is not None:
                    try:
                        prev_echo = bool(self._process.getecho())
                        if prev_echo != echo:
                            self._process.setecho(echo)
                            changed_echo = True
                    except Exception:
                        prev_echo = None
                        changed_echo = False

                self._process.send(text)
                self._last_activity_at = self._now_iso()
                self._last_output_time = time.monotonic()

                status = self._drain(
                    quiescence_ms=self._quiescence_ms if quiescence_ms is None else quiescence_ms,
                    timeout=timeout,
                    log=log,
                    capture=True,
                )
                output = self._capture_output()
                self._last_output_preview = output
                if log:
                    self._append_command(text)
                    self._append_interaction(text, output, status)
                    self._write_state()

                resp = {"status": status, "output": output}
                resp.update(self._capture_stats())
                if status == "error" and self._fatal_error:
                    resp["error"] = self._fatal_error
                return resp
            except Exception as e:
                self._fatal_error = f"{type(e).__name__}: {e}"
                return {"status": "error", "output": "", "error": self._fatal_error}
            finally:
                if changed_echo and prev_echo is not None:
                    try:
                        self._process.setecho(prev_echo)
                    except Exception:
                        pass

    def poll_output(
        self,
        timeout: float = 0.1,
        quiescence_ms: int | None = None,
        log: bool = True,
    ) -> dict:
        """Wait up to `timeout` seconds for new output without sending input."""
        with self._lock:
            self._fatal_error = None
            self._capture_reset()
            status = self._drain(
                quiescence_ms=self._quiescence_ms if quiescence_ms is None else quiescence_ms,
                timeout=timeout,
                log=log,
                capture=True,
                require_output=True,
            )

            output = self._capture_output()
            self._last_output_preview = output
            resp = {"status": status, "output": output}
            resp.update(self._capture_stats())
            if status == "error" and self._fatal_error:
                resp["error"] = self._fatal_error
            if output:
                self._last_activity_at = self._now_iso()
            return resp

    def send_signal(self, sig: int, timeout: float = 0.2, log: bool = True) -> dict:
        with self._lock:
            if not self.alive:
                return {"status": "eof", "output": "", "error": "pty not alive", "output_truncated": False, "dropped_bytes": 0}

            self._fatal_error = None
            self._capture_reset()

            pgid = None
            try:
                pgid = int(os.tcgetpgrp(self._process.fileno()))
            except Exception:
                pgid = None

            try:
                if pgid is not None:
                    os.killpg(pgid, sig)
                else:
                    os.kill(getattr(self._process, "pid", -1), sig)
            except Exception as e:
                self._fatal_error = f"{type(e).__name__}: {e}"
                resp = {"status": "error", "output": "", "error": self._fatal_error}
                resp.update(self._capture_stats())
                return resp

            self._last_activity_at = self._now_iso()
            status = self._drain(quiescence_ms=self._quiescence_ms, timeout=timeout, log=log, capture=True)
            output = self._capture_output()
            self._last_output_preview = output
            resp = {"status": status, "output": output}
            resp.update(self._capture_stats())
            return resp

    def expect(self, pattern: str, timeout: float = 30.0, log: bool = True) -> dict:
        """Wait until regex `pattern` appears in newly read output."""
        with self._lock:
            if not self.alive:
                return {"status": "eof", "output": "", "match": None, "groups": []}

            self._fatal_error = None
            self._capture_reset()

            try:
                rx = re.compile(pattern)
            except re.error as e:
                return {"status": "error", "output": "", "match": None, "groups": [], "error": f"re.error: {e}"}

            deadline = time.monotonic() + timeout
            buf = ""
            match_obj = None

            while True:
                now = time.monotonic()
                if now >= deadline:
                    out = self._capture_output()
                    if log:
                        self._append_interaction(f"[expect {pattern!r}]", out, "timeout")
                        self._write_state()
                    return {"status": "timeout", "output": out, **self._capture_stats(), "match": None, "groups": []}

                try:
                    chunk = self._process.read_nonblocking(size=4096, timeout=min(0.1, deadline - now))
                    if chunk:
                        self._last_output_time = time.monotonic()
                        buf += chunk
                        if len(buf) > 65536:
                            buf = buf[-65536:]
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
                        match_obj = rx.search(buf)
                        if match_obj:
                            out = self._capture_output()
                            if log:
                                self._append_interaction(f"[expect {pattern!r}]", out, "matched")
                                self._write_state()
                            self._last_activity_at = self._now_iso()
                            return {
                                "status": "matched",
                                "output": out,
                                **self._capture_stats(),
                                "match": match_obj.group(0),
                                "groups": list(match_obj.groups()),
                            }
                except pexpect.TIMEOUT:
                    continue
                except pexpect.EOF:
                    out = self._capture_output()
                    if log:
                        self._append_interaction(f"[expect {pattern!r}]", out, "eof")
                        self._write_state()
                    return {"status": "eof", "output": out, **self._capture_stats(), "match": None, "groups": []}
                except Exception as e:
                    self._fatal_error = f"{type(e).__name__}: {e}"
                    out = self._capture_output()
                    if log:
                        self._append_interaction(f"[expect {pattern!r}]", out, "error")
                        self._write_state()
                    return {
                        "status": "error",
                        "output": out,
                        **self._capture_stats(),
                        "match": None,
                        "groups": [],
                        "error": self._fatal_error,
                    }

    def screen_snapshot(self, log: bool = True, *, drain: bool = True) -> dict:
        with self._lock:
            if drain:
                self._drain_available(log=log)

            cursor_x = None
            cursor_y = None
            if self._vt100_ok:
                try:
                    cursor_x = int(getattr(self._screen.cursor, "x", 0))
                    cursor_y = int(getattr(self._screen.cursor, "y", 0))
                except Exception:
                    cursor_x = None
                    cursor_y = None

            if not self._vt100_ok:
                return {
                    "screen": self._last_output_preview,
                    "cursor_x": cursor_x,
                    "cursor_y": cursor_y,
                    "vt100_ok": self._vt100_ok,
                    "rows": self.rows,
                    "cols": self.cols,
                }

            lines: list[str] = []
            for line in self._screen.display:
                stripped = line.rstrip()
                if stripped or lines:
                    lines.append(stripped)

            while lines and not lines[-1]:
                lines.pop()

            return {
                "screen": "\n".join(lines),
                "cursor_x": cursor_x,
                "cursor_y": cursor_y,
                "vt100_ok": self._vt100_ok,
                "rows": self.rows,
                "cols": self.cols,
            }

    def read(self, log: bool = True) -> str:
        return self.screen_snapshot(log=log, drain=True)["screen"]

    def get_scrollback(self, lines: int = 200, log: bool = True, *, drain: bool = True) -> str:
        """Best-effort scrollback from VT100 history + current screen."""
        with self._lock:
            if drain:
                self._drain_available(log=log)
            if not self._vt100_ok:
                return self._last_output_preview

            cols = self.cols

            def render(line_dict: dict[int, pyte.screens.Char]) -> str:
                buf = [" "] * cols
                for i, ch in line_dict.items():
                    if 0 <= i < cols:
                        buf[i] = getattr(ch, "data", " ")
                return "".join(buf).rstrip()

            hist = []
            try:
                for line_dict in getattr(self._screen.history, "top", []):
                    hist.append(render(line_dict))
            except Exception:
                hist = []

            scr = [ln.rstrip() for ln in self._screen.display]
            full = [ln for ln in (hist + scr) if ln.strip() or True]
            if lines is None or lines <= 0:
                return "\n".join(full).rstrip("\n")
            return "\n".join(full[-lines:]).rstrip("\n")

    def clear_scrollback(self, log: bool = True):
        """Clear VT100 scrollback history without sending input to the PTY.

        This does not send Ctrl+L and does not modify the live terminal.
        It only clears the renderer's scrollback buffers while preserving the
        current visible display.
        """
        with self._lock:
            if log:
                self._append_command("[clear_scrollback]")
            if self._vt100_ok:
                try:
                    self._screen.history.top.clear()
                    self._screen.history.bottom.clear()
                except Exception:
                    self._screen = pyte.HistoryScreen(self.cols, self.rows, history=self._history_lines)
                    self._stream = pyte.Stream(_PyteListenerProxy(self._screen))
            self._last_activity_at = self._now_iso()
            self._write_state()

    def metadata(self) -> dict:
        pid = getattr(self._process, "pid", None)
        cwd = None
        if pid is not None:
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except Exception:
                cwd = None

        fg_pid = None
        try:
            fg_pid = int(os.tcgetpgrp(self._process.fileno()))
        except Exception:
            fg_pid = None

        return {
            "cwd": cwd,
            "pid": fg_pid,
            "shell_pid": pid,
            "cols": self.cols,
            "rows": self.rows,
            "started_at": self._started_at,
            "last_activity_at": self._last_activity_at,
            "description": self.description,
            "shell": self.shell,
            "shell_args": self.shell_args,
            "shell_prompt_regex": self.shell_prompt_regex,
        }

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

    def _drain(
        self,
        quiescence_ms: int | None = None,
        timeout: float = 30.0,
        log: bool = True,
        capture: bool = True,
        require_output: bool = False,
    ) -> str:
        if quiescence_ms is None:
            quiescence_ms = self._quiescence_ms
        deadline = time.monotonic() + timeout
        quiescence_s = quiescence_ms / 1000.0
        saw_output = False

        while True:
            now = time.monotonic()
            if now >= deadline:
                return "timeout"

            # Always attempt an immediate read first. Otherwise, if the session has
            # been idle long enough to be "quiescent", we could return without
            # noticing unread output that arrived since the last drain call.
            try:
                chunk = self._process.read_nonblocking(size=4096, timeout=0)
                if chunk:
                    self._last_output_time = time.monotonic()
                    saw_output = True
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
                    continue
            except pexpect.TIMEOUT:
                pass
            except pexpect.EOF:
                return "eof"
            except Exception as e:
                self._fatal_error = f"{type(e).__name__}: {e}"
                return "error"

            silence = now - self._last_output_time
            if (not require_output or saw_output) and silence >= quiescence_s:
                return "quiescent"

            time_until_deadline = deadline - now
            if require_output and not saw_output:
                read_timeout = min(time_until_deadline, 0.1)
            else:
                time_until_quiescent = quiescence_s - silence
                read_timeout = min(time_until_quiescent, time_until_deadline, 0.1)

            try:
                chunk = self._process.read_nonblocking(size=4096, timeout=read_timeout)
                if chunk:
                    self._last_output_time = time.monotonic()
                    saw_output = True
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

    def _drain_available(self, *, log: bool = True, capture: bool = False):
        while True:
            try:
                chunk = self._process.read_nonblocking(size=4096, timeout=0)
                if not chunk:
                    return
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
                return
            except pexpect.EOF:
                return
            except Exception as e:
                self._fatal_error = f"{type(e).__name__}: {e}"
                return

    def _capture_reset(self):
        self._full_lines: list[str] | None = []
        self._head_lines: list[str] = []
        self._tail_lines: deque[str] = deque(maxlen=self._context_lines)
        self._total_lines: int = 0
        self._line_buf: str = ""
        self._capture_total_bytes: int = 0

    def _capture_chunk(self, chunk: str):
        self._capture_total_bytes += len(chunk)
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

    def _capture_stats(self) -> dict:
        if self._full_lines is not None:
            captured_bytes = sum(len(s) for s in self._full_lines)
            truncated = False
        else:
            captured_bytes = sum(len(s) for s in self._head_lines) + sum(len(s) for s in self._tail_lines)
            truncated = True
        dropped = self._capture_total_bytes - captured_bytes
        if dropped < 0:
            dropped = 0
        return {"output_truncated": truncated, "dropped_bytes": int(dropped)}

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
            "start_time": self._started_at,
            "end_time": end_time,
            "pid": getattr(self._process, "pid", None),
            "initial_cwd": self._initial_cwd,
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
