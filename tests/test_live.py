"""Tests for the live performance monitor (fake readers, no performance counters)."""
import unittest

from wmm.agent import live


class Processes(unittest.TestCase):
    def test_top_processes_aggregates_instances(self):
        cpu = {"chrome": 20.0, "chrome#1": 30.0, "_Total": 800.0, "Idle": 700.0, "code": 8.0}
        memoria = {"chrome": 300 * 1024 ** 2, "chrome#1": 100 * 1024 ** 2, "code": 500 * 1024 ** 2, "_Total": 1.0}
        top = live.top_processes(cpu, memoria, cpus=8, n=2)
        self.assertEqual(top["cpu"], [{"name": "chrome", "cpu": 6.2}, {"name": "code", "cpu": 1.0}])
        self.assertEqual(top["memory"], [{"name": "code", "mb": 500}, {"name": "chrome", "mb": 400}])


class Monitor(unittest.TestCase):
    def test_samples_since(self):
        valori = iter(range(100))

        def reader():
            n = next(valori)
            return {"cpu": float(n), "processes": {"cpu": [], "memory": []}}

        orologio = iter(range(1000, 2000))
        monitor = live.LiveMonitor(reader, history=3, clock=lambda: next(orologio))
        for _ in range(5):
            monitor.sample_once()
        campioni = monitor.samples(0)
        self.assertEqual([c["cpu"] for c in campioni], [2.0, 3.0, 4.0])
        self.assertEqual([c["cpu"] for c in monitor.samples(campioni[1]["t"])], [4.0])

    def test_reader_error_is_skipped(self):
        def reader():
            raise OSError("counters unavailable")

        monitor = live.LiveMonitor(reader)
        monitor.sample_once()
        self.assertEqual(monitor.samples(0), [])
        self.assertIn("counters unavailable", monitor.last_error)

    def test_read_once_on_this_pc(self):
        # Smoke test of the real counters: values exist and stay in range.
        campione = live.SystemReader()()
        self.assertGreaterEqual(campione["memory_pct"], 0)
        self.assertLessEqual(campione["memory_pct"], 100)
        self.assertIn("cpu", campione)


if __name__ == "__main__":
    unittest.main()
