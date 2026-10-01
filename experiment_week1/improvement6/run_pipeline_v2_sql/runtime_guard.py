"""Small, stdlib-only startup guard for this memory-constrained workstation."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime
import ctypes
import hashlib
import os
from pathlib import Path
import sys
import time
import traceback

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = EXPERIMENT_DIR / ".runtime"


@contextmanager
def report_lock(report_path):
    """Lock only one report, allowing all eight distinct question types to run."""
    identity = os.path.normcase(str(Path(report_path).resolve()))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    path = RUNTIME_DIR / f"report_{digest}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(
                f"Another pipeline is writing this report: {report_path}. "
                "Use a different question type or output root in this terminal."
            ) from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def available_memory_mb():
    """Return available physical and commit memory on Windows, without psutil."""
    if os.name != "nt":
        return None
    from ctypes import wintypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [
            (name, ctypes.c_ulonglong) for name in (
                "total_phys", "avail_phys", "total_commit", "avail_commit",
                "total_virtual", "avail_virtual", "avail_extended",
            )
        ]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("Cannot read Windows memory status; pipeline startup stopped.")
    return status.avail_phys / 2**20, status.avail_commit / 2**20


def progress(message):
    print(message, file=sys.__stdout__, flush=True)


def wait_for_memory():
    """Wait before imports or another question; do not start more work under pressure."""
    announced = False
    while True:
        memory = available_memory_mb()
        if memory is None or (memory[0] >= 128 and memory[1] >= 1024):
            if announced:
                progress("[MEMORY] Available memory recovered; resuming.")
            return
        if not announced:
            progress(
                f"[PAUSED] Low memory: {memory[0]:.0f} MB physical, "
                f"{memory[1]:.0f} MB commit available. Close unused apps to resume "
                "(requires 128 MB physical and 1024 MB commit), or press Ctrl+C."
            )
            announced = True
        time.sleep(5)


def launch():
    """Guard before heavy imports and keep verbose output out of VS Code terminals."""
    try:
        wait_for_memory()
        # Resolve the report after loading the same configuration as the runner.
        from .common import REPORT_FILE
        with report_lock(REPORT_FILE):
            log_dir = RUNTIME_DIR / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"pipeline_{datetime.now():%Y%m%d_%H%M%S}_{os.getpid()}.log"
            progress(f"[RUNNING] Report: {REPORT_FILE}\n[LOG] {log_path}")
            try:
                with log_path.open("w", encoding="utf-8", buffering=1) as log:
                    with redirect_stdout(log), redirect_stderr(log):
                        try:
                            from .main import _main
                            _main()
                        except BaseException:
                            traceback.print_exc()
                            raise
            except KeyboardInterrupt:
                progress(f"[STOPPED] Interrupted. Details: {log_path}")
                raise SystemExit(130)
            except Exception:
                progress(f"[FAILED] Pipeline stopped. Read the traceback in: {log_path}")
                raise SystemExit(1)
            progress(f"[COMPLETE] Pipeline finished. Details: {log_path}")
    except RuntimeError as exc:
        progress(f"[BLOCKED] {exc}")
        raise SystemExit(75)

