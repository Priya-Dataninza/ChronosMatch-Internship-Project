import atexit
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from threading import RLock

from ipc.engine_status import read_engine_status


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_lock = RLock()
_engine_process = None
_engine_pid = None
_stop_file = None
_ready_file = None


def _process_is_running(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start_engine():
    global _engine_process, _engine_pid, _stop_file, _ready_file

    with _lock:
        if _engine_process is not None:
            if _engine_process.poll() is None:
                return {
                    "started": False,
                    "pid": _engine_pid or _engine_process.pid,
                }
            _clear_engine_process()

        status = read_engine_status()
        if status["status"] == "running" and _process_is_running(
            status.get("pid")
        ):
            return {"started": False, "pid": status["pid"]}
        if status["status"] == "stale" and _process_is_running(
            status.get("pid")
        ):
            raise RuntimeError(
                "The engine heartbeat is stale but its process is still "
                "running. Stop that process before starting another engine."
            )

        _stop_file = Path(tempfile.gettempdir()) / (
            f"chronosmatch_stop_{os.getpid()}_{uuid.uuid4().hex}"
        )
        _ready_file = Path(tempfile.gettempdir()) / (
            f"chronosmatch_ready_{os.getpid()}_{uuid.uuid4().hex}"
        )
        process_environment = os.environ.copy()
        process_environment["CHRONOS_STOP_FILE"] = str(_stop_file)
        process_environment["CHRONOS_READY_FILE"] = str(_ready_file)
        process_options = {
            "cwd": PROJECT_ROOT,
            "env": process_environment,
        }
        if sys.platform == "win32":
            process_options["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            process_options["start_new_session"] = True

        try:
            _engine_process = subprocess.Popen(
                [sys.executable, "-u", "-m", "ipc.engine_core"],
                **process_options,
            )
        except OSError:
            _clear_engine_process()
            raise

        started = False
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if _engine_process.poll() is not None:
                    _clear_engine_process()
                    raise RuntimeError(
                        "The matching engine exited during startup. Check "
                        "its console output and the Cython build."
                    )
                if _ready_file.exists():
                    engine_pid = int(
                        _ready_file.read_text(encoding="ascii")
                    )
                    status = read_engine_status()
                    if (
                        status["status"] == "running"
                        and status.get("pid") == engine_pid
                    ):
                        _engine_pid = engine_pid
                        started = True
                        return {"started": True, "pid": engine_pid}
                time.sleep(0.05)

            raise RuntimeError(
                "The matching engine did not publish a running heartbeat."
            )
        finally:
            if not started and _engine_process is not None:
                _stop_engine_process()


def _clear_engine_process():
    global _engine_process, _engine_pid, _stop_file, _ready_file
    if _stop_file is not None:
        _stop_file.unlink(missing_ok=True)
    if _ready_file is not None:
        _ready_file.unlink(missing_ok=True)
        _ready_file.with_name(_ready_file.name + ".tmp").unlink(
            missing_ok=True
        )
    _engine_process = None
    _engine_pid = None
    _stop_file = None
    _ready_file = None


def _stop_engine_process():
    if _engine_process is None:
        return False

    if _engine_process.poll() is None:
        _stop_file.touch()
        try:
            _engine_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _engine_process.terminate()
            try:
                _engine_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _engine_process.kill()
                _engine_process.wait(timeout=5)

    _clear_engine_process()
    return True


def stop_engine():
    with _lock:
        if _engine_process is not None:
            return {"stopped": _stop_engine_process()}

        status = read_engine_status()
        if status["status"] in {"running", "stale"}:
            raise RuntimeError(
                "This dashboard did not start the running engine. Stop it "
                "from the terminal that launched it."
            )
        return {"stopped": False}


def is_engine_managed():
    with _lock:
        return (
            _engine_process is not None
            and _engine_process.poll() is None
        )


def _shutdown_engine():
    if _engine_process is not None:
        stop_engine()


atexit.register(_shutdown_engine)
