"""Conservative CPU/thread configuration and telemetry for model training."""

from __future__ import annotations

import json
import math
import os
import threading
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator

import psutil


MAX_BLAS_THREADS = 16
OPENMP_THREADS = 1
RESERVED_PHYSICAL_CORE_FRACTION = 0.20
MONITOR_INTERVAL_SECONDS = 0.5


def make_thread_plan(
    physical_cores: int,
    logical_cpus: int,
    *,
    max_blas_threads: int = MAX_BLAS_THREADS,
    reserved_fraction: float = RESERVED_PHYSICAL_CORE_FRACTION,
) -> dict[str, int | float]:
    physical = max(1, int(physical_cores))
    logical = max(1, int(logical_cpus))
    reserve = max(1, math.ceil(physical * reserved_fraction))
    usable_physical = max(1, physical - reserve)
    blas = max(1, min(int(max_blas_threads), logical, usable_physical))
    return {
        "physical_cores": physical,
        "logical_cpus": logical,
        "reserved_physical_cores": min(reserve, physical - 1) if physical > 1 else 0,
        "usable_physical_cores": usable_physical,
        "blas_threads": blas,
        "openmp_threads": OPENMP_THREADS,
        "parallel_fit_jobs": 1,
        "reserved_fraction": reserved_fraction,
    }


def detect_hardware() -> dict[str, Any]:
    physical = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1
    logical = psutil.cpu_count(logical=True) or physical
    memory = psutil.virtual_memory()
    return {
        **make_thread_plan(physical, logical),
        "total_memory_bytes": int(memory.total),
        "available_memory_bytes": int(memory.available),
    }


def configure_thread_environment() -> dict[str, Any]:
    """Set native thread limits; call before importing NumPy/SciPy/scikit-learn."""
    hardware = detect_hardware()
    blas_threads = int(hardware["blas_threads"])
    environment = {
        "OPENBLAS_NUM_THREADS": str(blas_threads),
        "MKL_NUM_THREADS": str(blas_threads),
        "BLIS_NUM_THREADS": str(blas_threads),
        "VECLIB_MAXIMUM_THREADS": str(blas_threads),
        "NUMEXPR_NUM_THREADS": str(blas_threads),
        "OMP_NUM_THREADS": str(OPENMP_THREADS),
        "OMP_THREAD_LIMIT": str(OPENMP_THREADS),
        "LOKY_MAX_CPU_COUNT": str(hardware["usable_physical_cores"]),
    }
    os.environ.update(environment)
    return {**hardware, "environment": environment}


RUNTIME_CONFIG = configure_thread_environment()


def threadpool_snapshot() -> list[dict[str, Any]]:
    """Return effective BLAS/OpenMP pools after numerical libraries are imported."""
    from threadpoolctl import threadpool_info

    return [
        {
            "user_api": item.get("user_api"),
            "internal_api": item.get("internal_api"),
            "num_threads": item.get("num_threads"),
            "prefix": item.get("prefix"),
            "version": item.get("version"),
        }
        for item in threadpool_info()
    ]


@contextmanager
def numeric_thread_limits() -> Iterator[None]:
    """Apply the planned native limits at fit time, including already-loaded pools."""
    from threadpoolctl import threadpool_limits

    with ExitStack() as stack:
        stack.enter_context(
            threadpool_limits(limits=int(RUNTIME_CONFIG["blas_threads"]), user_api="blas")
        )
        stack.enter_context(
            threadpool_limits(limits=OPENMP_THREADS, user_api="openmp")
        )
        yield


class ResourceMonitor:
    """Sample process/system CPU and RSS during one training operation."""

    def __init__(
        self,
        label: str,
        *,
        interval_seconds: float = MONITOR_INTERVAL_SECONDS,
    ) -> None:
        self.label = label
        self.interval_seconds = interval_seconds
        self._process = psutil.Process(os.getpid())
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = 0.0
        self._process_cpu: list[float] = []
        self._host_cpu: list[float] = []
        self._rss_bytes: list[int] = []
        self._available_memory_bytes: list[int] = []
        self._sample_lock = threading.Lock()

    def __enter__(self) -> ResourceMonitor:
        self._started = time.perf_counter()
        psutil.cpu_percent(interval=None)
        self._process.cpu_percent(interval=None)
        self._sample()
        self._thread = threading.Thread(
            target=self._sample_loop,
            name=f"runtime-monitor-{self.label}",
            daemon=True,
        )
        self._thread.start()
        return self

    def _sample(self) -> None:
        try:
            process_cpu = self._process.cpu_percent(interval=None)
            host_cpu = psutil.cpu_percent(interval=None)
            rss = self._process.memory_info().rss
            available = psutil.virtual_memory().available
            with self._sample_lock:
                self._process_cpu.append(process_cpu)
                self._host_cpu.append(host_cpu)
                self._rss_bytes.append(int(rss))
                self._available_memory_bytes.append(int(available))
        except (psutil.Error, OSError):
            return

    def _sample_loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._sample()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 3))
        self._sample()

    def summary(self) -> dict[str, Any]:
        with self._sample_lock:
            process_cpu = list(self._process_cpu)
            host_cpu = list(self._host_cpu)
            rss = list(self._rss_bytes)
            available = list(self._available_memory_bytes)
        logical = int(RUNTIME_CONFIG["logical_cpus"])
        normalized_cpu = [value / logical for value in process_cpu]
        return {
            "label": self.label,
            "elapsed_seconds": max(0.0, time.perf_counter() - self._started),
            "sample_count": len(process_cpu),
            "process_cpu_percent_of_host_mean": (
                sum(normalized_cpu) / len(normalized_cpu) if normalized_cpu else 0.0
            ),
            "process_cpu_percent_of_host_peak": max(normalized_cpu, default=0.0),
            "host_cpu_percent_mean": sum(host_cpu) / len(host_cpu) if host_cpu else 0.0,
            "host_cpu_percent_peak": max(host_cpu, default=0.0),
            "peak_process_rss_bytes": max(rss, default=0),
            "minimum_available_memory_bytes": min(available, default=0),
            "logical_cpus_for_normalization": logical,
            "thread_configuration": {
                "blas_threads": RUNTIME_CONFIG["blas_threads"],
                "openmp_threads": OPENMP_THREADS,
                "parallel_fit_jobs": 1,
            },
        }


def main() -> None:
    import numpy
    import scipy
    from sklearn.linear_model import LogisticRegression

    _ = numpy.__version__, scipy.__version__, LogisticRegression
    print(json.dumps({**RUNTIME_CONFIG, "effective_threadpools": threadpool_snapshot()}, indent=2))


if __name__ == "__main__":
    main()