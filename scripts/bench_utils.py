import os
import platform
import statistics
import time
from pathlib import Path


def median_seconds(fn, repeats=3):
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    times, result = [], None
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - start)
    return statistics.median(times), result


def path_size(path):
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def machine_info():
    import pandas
    import pyarrow
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "pandas": pandas.__version__,
        "pyarrow": pyarrow.__version__,
        "cpu_count": os.cpu_count(),
    }
