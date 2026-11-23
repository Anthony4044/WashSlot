"""Send several requests at the same moment, as many customers (or one double-clicking customer) would."""
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import httpx


def at_once(n: int, send: Callable[[int], httpx.Response]) -> list[httpx.Response]:
    """Call send(i) for i = 0..n-1 in n threads that wait at a barrier and then all go together.

    Returns the n responses in order. httpx.Client is thread-safe, so the threads may share one.
    """
    start_line = threading.Barrier(n)

    def run(i: int) -> httpx.Response:
        start_line.wait(timeout=30)
        return send(i)

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(run, range(n)))
