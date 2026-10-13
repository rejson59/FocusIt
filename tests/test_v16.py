"""Testy v1.6: rozbudowany benchmark, inwentaryzacja, raport Windows."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from focusit.core import (BenchmarkResult2, benchmark_disk_random,
                          benchmark_ram_latency, benchmark_sustained_cpu,
                          hardware_inventory, performance_findings,
                          run_benchmark2, windows_optimization_report)


class TestExtendedBenchmark(unittest.TestCase):
    def test_pieces(self):
        self.assertGreater(benchmark_ram_latency(rounds=20_000), 0)
        iops = benchmark_disk_random(size_mb=8, ops=100)
        self.assertGreater(iops, 0)
        first, drop = benchmark_sustained_cpu(rounds=2, duration=0.15)
        self.assertGreater(first, 0)
        self.assertGreaterEqual(drop, 0)

    def test_full_benchmark2_classifies(self):
        r = run_benchmark2(progress=lambda m: None)
        self.assertIsInstance(r, BenchmarkResult2)
        self.assertIn(r.tier, ("Słaby", "Średni", "Mocny", "Top"))
        self.assertGreater(r.cpu_multi_mbs, 0)
        self.assertGreater(r.disk_read_mbs, 0)

    def test_findings_for_weak_pc(self):
        weak = BenchmarkResult2(cpu_single_mbs=100, cpu_multi_mbs=200,
                                cpu_scaling_pct=30, cpu_sustained_drop_pct=25,
                                ram_latency_ns=220, ram_total_gb=8,
                                disk_random_iops=300)
        findings = performance_findings(weak)
        text = " ".join(findings)
        self.assertIn("THROTTLING", text)
        self.assertIn("XMP", text)
        self.assertIn("HDD", text)


class TestInventoryAndReport(unittest.TestCase):
    def test_inventory_shape(self):
        info = hardware_inventory()
        for key in ("cpu", "cpu_cores", "ram_modules", "gpus", "os"):
            self.assertIn(key, info)
        self.assertGreaterEqual(info["cpu_cores"], 1)

    def test_windows_report_safe_everywhere(self):
        report = windows_optimization_report()
        self.assertTrue(report)
        for row in report:
            for key in ("name", "status", "advice", "level"):
                self.assertIn(key, row)


if __name__ == "__main__":
    unittest.main()
