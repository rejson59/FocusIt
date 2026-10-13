"""Testy v1.3: kondycja PC, usługi Windows (fake runner), obciążenie tła."""

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from focusit.core import (SERVICE_CANDIDATES, ProcessInfo,
                          compute_health_score, measure_background_load,
                          service_state, start_services,
                          stop_services_for_session)


def P(name="app.exe", mem=100.0):
    return ProcessInfo(pid=99991, name=name, exe=r"C:\Aplikacje\app.exe",
                       memory_mb=mem)


class FakeRunner:
    """Udaje `sc`: query zwraca RUNNING, stop zmienia stan, start przywraca."""

    def __init__(self):
        self.running = set(SERVICE_CANDIDATES)
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        action, name = args[1], args[2]
        if action == "query":
            state = "RUNNING" if name in self.running else "STOPPED"
            out = f"        STATE              : 4  {state}\n"
            return subprocess.CompletedProcess(args, 0, out, "")
        if action == "stop":
            self.running.discard(name)
        if action == "start":
            self.running.add(name)
        return subprocess.CompletedProcess(args, 0, "", "")


class TestServices(unittest.TestCase):
    def test_state_parse(self):
        runner = FakeRunner()
        self.assertEqual(service_state("DiagTrack", runner), "RUNNING")

    def test_stop_and_start_only_known_services(self):
        import focusit.core as core
        runner = FakeRunner()
        original = core.sys.platform
        core.sys.platform = "win32"
        try:
            stopped = stop_services_for_session(
                ["DiagTrack", "NieznanaUsluga"], log=lambda m: None,
                runner=runner)
            self.assertEqual(stopped, ["DiagTrack"])
            self.assertNotIn("DiagTrack", runner.running)
            start_services(stopped, log=lambda m: None, runner=runner)
            self.assertIn("DiagTrack", runner.running)
        finally:
            core.sys.platform = original


class TestHealthScore(unittest.TestCase):
    def test_clean_pc_scores_high(self):
        score, tips = compute_health_score(
            {"ram_percent": 40, "process_count": 80},
            {"size_mb": 10}, autostart_count=3, heavy_processes=[])
        self.assertGreaterEqual(score, 90)
        self.assertTrue(any("Świetna kondycja" in t for t in tips))

    def test_dirty_pc_scores_low_with_tips(self):
        heavy = [P("chrome.exe", 900), P("spotify.exe", 400), P("discord.exe", 500)]
        score, tips = compute_health_score(
            {"ram_percent": 92, "process_count": 210},
            {"size_mb": 2500}, autostart_count=16, heavy_processes=heavy)
        self.assertLessEqual(score, 40)
        self.assertGreaterEqual(len(tips), 4)


class TestBackgroundLoad(unittest.TestCase):
    def test_measure_returns_sane_value(self):
        value = measure_background_load(sample_seconds=0.1)
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 100.0)


if __name__ == "__main__":
    unittest.main()
