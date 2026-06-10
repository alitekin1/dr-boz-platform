from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_started_at: datetime | None = None


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bot_log_path() -> Path:
    return Path("/tmp/jgpti-telegram-bot.log")


def _env_file_path() -> Path:
    return _backend_root() / ".env"


def _load_bot_env_overrides() -> dict[str, str]:
    env_path = _env_file_path()
    if not env_path.exists():
        return {}
    loaded = dotenv_values(env_path)
    overrides: dict[str, str] = {}
    for key, value in loaded.items():
        if not key or value is None:
            continue
        overrides[str(key)] = str(value)
    return overrides


def _find_external_bot_pids() -> list[int]:
    """Find all PIDs related to the bot or its watcher, excluding the current process."""
    try:
        # Match "app.bot" (the bot module) or "bot_watcher.py" (the persistent watcher)
        # We use a broad pattern to ensure we catch all related processes
        cmd = ["pgrep", "-f", "app.bot|bot_watcher.py"]
        out = subprocess.check_output(cmd, text=True).strip()
    except Exception:
        return []
    
    if not out:
        return []
        
    pids = []
    my_pid = os.getpid()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
            if pid != my_pid:
                pids.append(pid)
        except ValueError:
            continue
    return sorted(list(set(pids)))


def _is_pid_running(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_bot_status() -> dict[str, Any]:
    with _lock:
        global _proc
        if _proc is not None and _proc.poll() is not None:
            _proc = None

        if _proc is not None:
            return {
                "running": True,
                "pid": _proc.pid,
                "managed": True,
                "started_at": _started_at.isoformat() if _started_at else None,
                "detail": "running",
            }

    external_pids = _find_external_bot_pids()
    if external_pids:
        return {
            "running": True,
            "pid": external_pids[0],
            "all_pids": external_pids,
            "managed": False,
            "started_at": None,
            "detail": f"running ({len(external_pids)} external process{'es' if len(external_pids) > 1 else ''})",
        }
        
    return {
        "running": False,
        "pid": None,
        "managed": False,
        "started_at": None,
        "detail": "stopped",
    }


_SYSTEMD_SERVICE = "jgpti-telegram-bot.service"


def _run_systemctl(*args: str) -> bool:
    """Run a systemctl command. Returns True if successful."""
    try:
        subprocess.run(
            ["systemctl", *args],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _stop_systemd_bot() -> None:
    """Stop and disable the systemd bot service to prevent it from restarting."""
    _run_systemctl("stop", _SYSTEMD_SERVICE)
    _run_systemctl("disable", _SYSTEMD_SERVICE)


def _kill_watcher_processes() -> None:
    """Kill any bot_watcher.py processes to prevent duplicate bot instances."""
    try:
        cmd = ["pgrep", "-f", "bot_watcher.py"]
        out = subprocess.check_output(cmd, text=True).strip()
        if not out:
            return
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pid = int(line)
                if pid != os.getpid():
                    os.kill(pid, signal.SIGKILL)
            except ValueError:
                continue
            except OSError:
                pass
    except Exception:
        pass


def _kill_all_bot_processes() -> None:
    """Force kill all bot-related processes."""
    try:
        cmd = ["pgrep", "-f", "app.bot"]
        out = subprocess.check_output(cmd, text=True).strip()
        if not out:
            return
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pid = int(line)
                if pid != os.getpid():
                    os.kill(pid, signal.SIGKILL)
            except ValueError:
                continue
            except OSError:
                pass
    except Exception:
        pass


def start_bot() -> dict[str, Any]:
    with _lock:
        global _proc, _started_at
        # If we have a managed process already
        if _proc is not None and _proc.poll() is None:
            return {
                "running": True,
                "pid": _proc.pid,
                "managed": True,
                "started_at": _started_at.isoformat() if _started_at else None,
                "detail": "already running",
            }

        # Prevent systemd and watcher from spawning duplicate bots
        _stop_systemd_bot()
        _kill_watcher_processes()
        _kill_all_bot_processes()
        time.sleep(0.5)

        # Verify no external bot processes remain
        external_pids = _find_external_bot_pids()
        if external_pids:
            return {
                "running": True,
                "pid": external_pids[0],
                "all_pids": external_pids,
                "managed": False,
                "started_at": None,
                "detail": f"already running ({len(external_pids)} external process{'es' if len(external_pids) > 1 else ''})",
            }

        env = os.environ.copy()
        env.update(_load_bot_env_overrides())
        env["PYTHONUNBUFFERED"] = "1"
        log_file = _bot_log_path().open("ab")
        try:
            _proc = subprocess.Popen(
                [sys.executable, "-m", "app.bot"],
                cwd=str(_backend_root()),
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
            _started_at = datetime.now(timezone.utc)
        finally:
            log_file.close()

    time.sleep(0.8)
    return get_bot_status()


def stop_bot() -> dict[str, Any]:
    with _lock:
        global _proc, _started_at
        # 1. Stop managed process
        if _proc is not None and _proc.poll() is None:
            try:
                _proc.terminate()
                _proc.wait(timeout=5)
            except Exception:
                try:
                    _proc.kill()
                    _proc.wait(timeout=2)
                except Exception:
                    pass
            finally:
                _proc = None
                _started_at = None

    # 2. Stop systemd service so it doesn't restart the bot
    _stop_systemd_bot()

    # 3. Kill watcher and all bot processes
    _kill_watcher_processes()
    _kill_all_bot_processes()

    # 4. Retry killing to catch any respawns
    for attempt in range(3):
        external_pids = _find_external_bot_pids()
        if not external_pids:
            break
        for pid in external_pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        time.sleep(0.5)

    return get_bot_status()
