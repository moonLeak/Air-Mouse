from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

STATE_DIR = Path.home() / ".airmouse"
PID_FILE = STATE_DIR / "airmouse.pid"
LOG_FILE = STATE_DIR / "airmouse.log"


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _read_pid() -> Optional[int]:
    try:
        data = PID_FILE.read_text(encoding="utf-8").strip()
        return int(data)
    except (FileNotFoundError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    PID_FILE.write_text(str(pid), encoding="utf-8")


def _clear_pid() -> None:
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _stop_process(pid: int, timeout: float = 5.0) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _is_process_alive(pid):
            return True
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    return not _is_process_alive(pid)


def _start_process() -> int:
    _ensure_state_dir()
    env = os.environ.copy()
    env.setdefault("MEDIAPIPE_DISABLE_GPU", "1")

    log_handle = open(LOG_FILE, "a", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "airmouse"],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env,
    )
    _write_pid(process.pid)
    log_handle.write("\n=== AirMouse started (pid={}) ===\n".format(process.pid))
    log_handle.flush()
    log_handle.close()
    return process.pid


def toggle() -> None:
    _ensure_state_dir()
    pid = _read_pid()
    if pid and _is_process_alive(pid):
        stopped = _stop_process(pid)
        _clear_pid()
        with open(LOG_FILE, "a", encoding="utf-8") as log_handle:
            log_handle.write("\n=== AirMouse stopped (pid={}) success={} ===\n".format(pid, stopped))
        status = "stopped" if stopped else "stopping failed"
        print(f"AirMouse {status} (pid={pid})")
        return

    if pid and not _is_process_alive(pid):
        _clear_pid()

    new_pid = _start_process()
    print(f"AirMouse started (pid={new_pid})")


def main() -> None:
    toggle()


if __name__ == "__main__":
    main()
