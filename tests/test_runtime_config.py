from __future__ import annotations

import os
import unittest

from src.runtime_config import (
    MAX_BLAS_THREADS,
    OPENMP_THREADS,
    RUNTIME_CONFIG,
    make_thread_plan,
    numeric_thread_limits,
    threadpool_snapshot,
)


class RuntimeConfigTests(unittest.TestCase):
    def test_thread_plan_reserves_physical_cores_and_prevents_nesting(self) -> None:
        plan = make_thread_plan(20, 28)
        self.assertEqual(plan["physical_cores"], 20)
        self.assertEqual(plan["logical_cpus"], 28)
        self.assertEqual(plan["reserved_physical_cores"], 4)
        self.assertEqual(plan["blas_threads"], 16)
        self.assertEqual(plan["openmp_threads"], 1)
        self.assertEqual(plan["parallel_fit_jobs"], 1)

    def test_small_hosts_keep_at_least_one_usable_worker(self) -> None:
        for physical, logical in ((1, 1), (2, 2), (4, 8)):
            plan = make_thread_plan(physical, logical)
            self.assertGreaterEqual(plan["blas_threads"], 1)
            self.assertLessEqual(plan["blas_threads"], logical)
            self.assertLessEqual(plan["blas_threads"], physical)
            self.assertEqual(plan["openmp_threads"], OPENMP_THREADS)
        self.assertLessEqual(MAX_BLAS_THREADS, 16)

    def test_environment_limits_are_set_on_runtime_import(self) -> None:
        self.assertEqual(os.environ["OPENBLAS_NUM_THREADS"], str(RUNTIME_CONFIG["blas_threads"]))
        self.assertEqual(os.environ["OMP_NUM_THREADS"], "1")
        self.assertEqual(os.environ["OMP_THREAD_LIMIT"], "1")
        self.assertEqual(os.environ["MKL_NUM_THREADS"], str(RUNTIME_CONFIG["blas_threads"]))

    def test_loaded_native_pools_respect_fit_time_limits_without_fitting(self) -> None:
        import numpy
        import scipy
        from sklearn.linear_model import LogisticRegression

        _ = numpy.__version__, scipy.__version__, LogisticRegression
        with numeric_thread_limits():
            pools = threadpool_snapshot()
        self.assertTrue(pools)
        self.assertTrue(
            all(
                pool["num_threads"] <= RUNTIME_CONFIG["blas_threads"]
                for pool in pools
                if pool["user_api"] == "blas"
            )
        )
        self.assertTrue(
            all(
                pool["num_threads"] == OPENMP_THREADS
                for pool in pools
                if pool["user_api"] == "openmp"
            )
        )


if __name__ == "__main__":
    unittest.main()