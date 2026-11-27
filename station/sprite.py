"""Talk to the Sprite runtime: keep it awake during a build (Tasks API), take checkpoints.

Tasks API (docs.fly.io/sprites/keeping-sprites-running): PUT http://sprite/v1/tasks/<name>
over /.sprite/api.sock creates or refreshes a hold (max 1 h); DELETE releases it.
"""
from __future__ import annotations

import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

SOCKET = Path("/.sprite/api.sock")


def _curl(args: list[str], timeout: float = 15) -> None:
    # Best effort: a slow control socket must not crash a build that already published (Nov 27).
    try:
        subprocess.run(args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        pass


def _cmd(socket: Path, method: str, name: str, body: str | None = None) -> list[str]:
    args = ["curl", "-s", "--unix-socket", str(socket), "-X", method, "-H", "Content-Type: application/json"]
    if body:
        args += ["-d", body]
    return args + [f"http://sprite/v1/tasks/{name}"]


@contextmanager
def hold(name: str = "build", expire: str = "5m", socket: Path = SOCKET, interval_s: float = 60,
         runner: Callable[[list[str]], None] = _curl):
    """Hold the Sprite awake while the block runs: refresh every minute, release on exit.

    No-op outside a Sprite (no socket), e.g. in tests or on a laptop.
    """
    if not Path(socket).exists():
        yield
        return
    stop = threading.Event()
    body = f'{{"expire": "{expire}"}}'

    def beat():
        while not stop.is_set():
            runner(_cmd(socket, "PUT", name, body))
            stop.wait(interval_s)

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)
        runner(_cmd(socket, "DELETE", name))
