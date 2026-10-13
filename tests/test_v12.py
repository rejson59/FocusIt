"""Testy v1.2: zamrażanie, powinowactwo CPU, wersje, odzyskiwanie po awarii."""

import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psutil

from focusit.core import (FocusSession, FocusStore, is_newer_version,
                          parse_affinity, parse_version,
                          recover_previous_session)


class TestAffinityAndVersions(unittest.TestCase):
    def test_parse_affinity(self):
        self.assertEqual(parse_affinity("0-1,1"), [0, 1])
        self.assertEqual(parse_affinity("0"), [0])
        self.assertEqual(parse_affinity(""), [])
        self.assertEqual(parse_affinity("abc, 0"), [0])
        self.assertTrue(all(c < (psutil.cpu_count() or 64)
                            for c in parse_affinity("0-999")))

    def test_versions(self):
        self.assertEqual(parse_version("v1.10.2"), (1, 10, 2))
        self.assertTrue(is_newer_version("v1.2.0", "1.1.0"))
        self.assertFalse(is_newer_version("v1.1.0", "1.1.0"))
        self.assertFalse(is_newer_version("v1.0.9", "1.1.0"))


class TestFreezeSession(unittest.TestCase):
    def test_freeze_and_resume_real_process(self):
        victim = subprocess.Popen(["sleep", "30"], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.3)
            preset = {"name": "Test", "mode": "gentle",
                      "close_apps": ["sleep"], "keep_apps": [],
                      "freeze_processes": True,
                      "power_high_performance": False, "raise_priority": False}
            session = FocusSession(preset, {}, target_name="python3",
                                   log=lambda m: None)
            result = session.start(simulate=False)
            # na maszynie testowej mogą istnieć inne procesy "sleep" z wcześniejszych testów
            self.assertGreaterEqual(len(result.suspended), 1)
            time.sleep(0.4)   # SIGSTOP potrzebuje chwili
            self.assertEqual(psutil.Process(victim.pid).status(),
                             psutil.STATUS_STOPPED)
            self.assertEqual(result.killed, [])
            summary = session.stop()
            time.sleep(0.2)
            self.assertGreaterEqual(summary["suspended_count"], 1)
            self.assertNotEqual(psutil.Process(victim.pid).status(),
                                psutil.STATUS_STOPPED)
        finally:
            victim.terminate()


class TestCrashRecovery(unittest.TestCase):
    def test_recover_resumes_suspended_and_clears_state(self):
        import tempfile
        victim = subprocess.Popen(["sleep", "30"], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.3)
            psutil.Process(victim.pid).suspend()
            with tempfile.TemporaryDirectory() as tmp:
                store = FocusStore(directory=Path(tmp))
                store.settings["restore_apps_after_session"] = False
                store.save_session_state({
                    "preset": "Gry", "suspended_pids": [victim.pid],
                    "killed_exes": [], "power_guid": None})
                self.assertTrue(store.load_session_state())
                messages = recover_previous_session(store, log=lambda m: None)
                self.assertTrue(any("Odmrożono" in m for m in messages))
                self.assertNotEqual(psutil.Process(victim.pid).status(),
                                    psutil.STATUS_STOPPED)
                self.assertEqual(store.load_session_state(), {})
        finally:
            victim.terminate()


if __name__ == "__main__":
    unittest.main()
