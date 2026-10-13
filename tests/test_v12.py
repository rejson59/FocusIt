"""Testy v1.2: zamrażanie, powinowactwo CPU, wersje, odzyskiwanie po awarii.

Wieloplatformowe: procesem-ofiarą jest python -c "sleep", a nie uniksowy
program `sleep` (którego nie ma na Windowsie).
"""

import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psutil

from focusit.core import (Decision, FocusSession, FocusStore, KillPlan,
                          ProcessInfo, is_newer_version, is_suspended,
                          list_processes, parse_affinity, parse_version,
                          recover_previous_session)


def spawn_victim() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def victim_info(pid: int) -> ProcessInfo:
    for p in list_processes():
        if p.pid == pid:
            return p
    raise AssertionError("nie znaleziono procesu ofiary")


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
        victim = spawn_victim()
        try:
            time.sleep(0.3)
            preset = {"name": "Test", "mode": "gentle", "close_apps": [],
                      "keep_apps": [], "freeze_processes": True,
                      "power_high_performance": False, "raise_priority": False}
            session = FocusSession(preset, {}, target_name="inna-gra",
                                   log=lambda m: None)
            # plan wskazuje dokładnie ofiarę (bez ryzyka dla procesu testów)
            info = victim_info(victim.pid)
            session.plan = KillPlan([Decision(info, "kill", "test", "Test")])
            result = session.start(simulate=False)
            self.assertEqual([p.pid for p in result.suspended], [victim.pid])
            self.assertEqual(result.killed, [])
            time.sleep(0.4)   # sygnał STOP potrzebuje chwili
            self.assertTrue(is_suspended(psutil.Process(victim.pid)))
            summary = session.stop()
            time.sleep(0.2)
            self.assertEqual(summary["suspended_count"], 1)
            self.assertFalse(is_suspended(psutil.Process(victim.pid)))
        finally:
            victim.terminate()


class TestCrashRecovery(unittest.TestCase):
    def test_recover_resumes_suspended_and_clears_state(self):
        import tempfile
        victim = spawn_victim()
        try:
            time.sleep(0.3)
            psutil.Process(victim.pid).suspend()
            time.sleep(0.3)
            with tempfile.TemporaryDirectory() as tmp:
                store = FocusStore(directory=Path(tmp))
                store.settings["restore_apps_after_session"] = False
                store.save_session_state({
                    "preset": "Gry", "suspended_pids": [victim.pid],
                    "killed_exes": [], "power_guid": None})
                self.assertTrue(store.load_session_state())
                messages = recover_previous_session(store, log=lambda m: None)
                time.sleep(0.2)
                self.assertTrue(any("Odmrożono" in m for m in messages))
                self.assertFalse(is_suspended(psutil.Process(victim.pid)))
                self.assertEqual(store.load_session_state(), {})
        finally:
            victim.terminate()


if __name__ == "__main__":
    unittest.main()
