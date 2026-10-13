"""Testy silnika FocusIt — szczególnie reguł bezpieczeństwa trybu izolacji."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from focusit.core import (ProcessInfo, FocusStore, compute_plan,
                          is_hard_protected, is_system_path)


def proc(pid, name, exe="", ppid=0, user="DESKTOP\\Gracz", mem=100.0):
    return ProcessInfo(pid=pid, ppid=ppid, name=name, exe=exe,
                       username=user, memory_mb=mem, create_time=1000.0 + pid)


OWN = 9999


def base_processes():
    return [
        proc(4, "System", r"C:\Windows\System32\ntoskrnl.exe", user="NT AUTHORITY\\SYSTEM"),
        proc(500, "svchost.exe", r"C:\Windows\System32\svchost.exe", user="NT_AUTHORITY\\SYSTEM"),
        proc(600, "dwm.exe", r"C:\Windows\System32\dwm.exe", user="Window Manager\\DWM-1"),
        proc(700, "explorer.exe", r"C:\Windows\explorer.exe"),
        proc(800, "MsMpEng.exe", r"C:\Program Files\Windows Defender\MsMpEng.exe",
             user="NT AUTHORITY\\SYSTEM"),
        proc(900, "nvcontainer.exe", r"C:\Program Files\NVIDIA\nvcontainer.exe"),
        proc(1000, "game.exe", r"D:\Gry\MojaGra\game.exe", mem=4000.0),
        proc(1001, "EasyAntiCheat.exe", r"D:\Gry\MojaGra\EasyAntiCheat.exe", ppid=1000),
        proc(1002, "steam.exe", r"C:\Program Files (x86)\Steam\steam.exe", ppid=0),
        proc(1100, "chrome.exe", r"C:\Program Files\Google\Chrome\chrome.exe", mem=1500.0),
        proc(1200, "spotify.exe", r"C:\Users\Gracz\AppData\Spotify\spotify.exe", mem=300.0),
        proc(1300, "discord.exe", r"C:\Users\Gracz\AppData\Discord\discord.exe", mem=400.0),
        proc(1400, "unknownapp.exe", "", mem=50.0),          # brak ścieżki -> chroniony
        proc(1500, "mystery.exe", r"C:\Users\Gracz\Apps\mystery.exe",
             user="NT_AUTHORITY\\SYSTEM"),                  # konto systemowe -> chroniony
        proc(OWN, "FocusIt.exe", r"C:\Programy\FocusIt\FocusIt.exe"),
    ]


def decisions_by_name(plan):
    return {d.proc.name: d for d in plan.decisions}


class TestSafetyClassification(unittest.TestCase):
    def test_system_path_detection(self):
        self.assertTrue(is_system_path(r"C:\Windows\System32\svchost.exe"))
        self.assertTrue(is_system_path(r"c:\windows\explorer.exe"))
        self.assertFalse(is_system_path(r"D:\Gry\game.exe"))

    def test_hard_protected(self):
        self.assertIsNotNone(is_hard_protected(base_processes()[1]))   # svchost
        self.assertIsNotNone(is_hard_protected(proc(2000, "csrss.exe", r"C:\Windows\System32\csrss.exe")))
        self.assertIsNone(is_hard_protected(proc(2001, "chrome.exe",
                                                 r"C:\Program Files\Google\Chrome\chrome.exe")))


class TestIsolationPlan(unittest.TestCase):
    def setUp(self):
        self.plan = compute_plan(base_processes(), target_name="game.exe",
                                 mode="isolation",
                                 keep_names=["discord.exe"], own_pid=OWN)
        self.d = decisions_by_name(self.plan)

    def test_never_kills_system(self):
        for name in ("svchost.exe", "dwm.exe", "explorer.exe", "MsMpEng.exe",
                     "nvcontainer.exe", "unknownapp.exe", "mystery.exe"):
            self.assertEqual(self.d[name].action, "keep", f"{name} musi zostać zachowany")

    def test_keeps_target_and_related(self):
        self.assertEqual(self.d["game.exe"].action, "keep")
        self.assertEqual(self.d["game.exe"].category, "Cel")
        # proces potomny gry (anti-cheat) z tego samego folderu
        self.assertEqual(self.d["EasyAntiCheat.exe"].action, "keep")

    def test_keeps_user_whitelist_and_self(self):
        self.assertEqual(self.d["discord.exe"].action, "keep")
        self.assertEqual(self.d["FocusIt.exe"].action, "keep")

    def test_kills_unrelated_user_apps(self):
        self.assertEqual(self.d["chrome.exe"].action, "kill")
        self.assertEqual(self.d["spotify.exe"].action, "kill")

    def test_never_kills_other_users_processes(self):
        procs = base_processes() + [
            proc(1600, "rootdaemon", "/usr/bin/rootdaemon", user="root"),
            proc(1601, "otheruserapp.exe", r"C:\Users\Inny\app.exe",
                 user="DESKTOP\\Inny"),
        ]
        plan = compute_plan(procs, target_name="game.exe", mode="isolation",
                            own_pid=OWN, current_username="DESKTOP\\Gracz")
        d = decisions_by_name(plan)
        self.assertEqual(d["rootdaemon"].action, "keep")
        self.assertEqual(d["otheruserapp.exe"].action, "keep")
        # a proces bieżącego użytkownika nadal jest zamykany
        self.assertEqual(d["chrome.exe"].action, "kill")

    def test_estimated_freed_ram(self):
        # chrome 1500 + spotify 300 (steam też niezwiązany -> kill bez keep-listy launchera tu)
        self.assertGreaterEqual(self.plan.estimated_freed_mb, 1800.0)


class TestGentlePlan(unittest.TestCase):
    def test_gentle_kills_only_listed(self):
        plan = compute_plan(base_processes(), target_name="game.exe", mode="gentle",
                            close_names=["spotify.exe"], keep_names=[], own_pid=OWN)
        d = decisions_by_name(plan)
        self.assertEqual(d["spotify.exe"].action, "kill")
        self.assertEqual(d["chrome.exe"].action, "keep")
        # nawet w gentle proces systemowy z listy nie zostanie zabity
        plan2 = compute_plan(base_processes(), mode="gentle",
                             close_names=["svchost.exe"], own_pid=OWN)
        self.assertEqual(decisions_by_name(plan2)["svchost.exe"].action, "keep")


class TestStore(unittest.TestCase):
    def test_presets_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["FOCUSIT_HOME"] = tmp
            store = FocusStore(directory=Path(tmp))
            self.assertTrue(any(p["name"] == "Gry" for p in store.presets))
            custom = dict(store.presets[0])
            custom["name"] = "Moje Gry"
            custom["built_in"] = False
            store.upsert_preset(custom)
            store2 = FocusStore(directory=Path(tmp))
            self.assertIsNotNone(store2.get_preset("Moje Gry"))
            self.assertTrue(store2.delete_preset("Moje Gry"))
            self.assertFalse(store2.delete_preset("Gry"))  # wbudowanego nie usuwamy


if __name__ == "__main__":
    unittest.main()
