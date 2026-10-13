"""Testy nowych funkcji v1.1: biblioteka gier, czyszczenie temp, profile gier."""

import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from focusit.core import (FocusStore, GameEntry, parse_acf,
                          parse_epic_manifest, preview_temp_clean,
                          execute_temp_clean, get_gpu_stats)


class TestSteamParsing(unittest.TestCase):
    def test_parse_acf(self):
        acf = '''"AppState"
        {
            "appid"		"730"
            "name"		"Counter-Strike 2"
            "installdir"		"Counter-Strike Global Offensive"
        }'''
        data = parse_acf(acf)
        self.assertEqual(data["appid"], "730")
        self.assertEqual(data["name"], "Counter-Strike 2")
        self.assertEqual(data["installdir"], "Counter-Strike Global Offensive")


class TestEpicParsing(unittest.TestCase):
    def test_parse_epic_manifest(self):
        entry = parse_epic_manifest({
            "DisplayName": "Fortnite",
            "InstallLocation": "C:\\Epic\\Fortnite",
            "LaunchExecutable": "FortniteGame/Binaries/Win64/FortniteClient.exe",
        })
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "Fortnite")
        self.assertEqual(entry.platform, "Epic")
        self.assertTrue(entry.exe.replace("/", "\\").endswith("FortniteClient.exe"))

    def test_epic_manifest_without_name(self):
        self.assertIsNone(parse_epic_manifest({"InstallLocation": "C:\\X"}))


class TestTempClean(unittest.TestCase):
    def test_preview_and_clean_only_old_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            old = base / "old.tmp"
            new = base / "new.tmp"
            old.write_bytes(b"x" * 3 * 1024 * 1024)
            new.write_bytes(b"y" * 1024)
            past = time.time() - 48 * 3600
            os.utime(old, (past, past))
            preview = preview_temp_clean(dirs=[base], older_than_hours=24)
            self.assertEqual(preview["files"], 1)
            self.assertGreater(preview["size_mb"], 0)
            result = execute_temp_clean(dirs=[base], older_than_hours=24)
            self.assertEqual(result["removed"], 1)
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())   # świeży plik zostaje!


class TestGameProfilesAndGpu(unittest.TestCase):
    def test_game_profile_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            store = FocusStore(directory=Path(tmp))
            store.set_game_profile(r"D:\Gry\game.exe",
                                   {"mode": "isolation", "keep_apps": ["discord.exe"]})
            store2 = FocusStore(directory=Path(tmp))
            prof = store2.game_profile(r"d:\gry\GAME.EXE")
            self.assertEqual(prof["mode"], "isolation")
            self.assertEqual(prof["keep_apps"], ["discord.exe"])

    def test_gpu_stats_returns_dict_or_none(self):
        stats = get_gpu_stats()   # na maszynie bez NVIDIA zwraca None — też OK
        self.assertTrue(stats is None or
                        ("percent" in stats and "temp_c" in stats))

    def test_game_entry_stem(self):
        g = GameEntry(name="Gra", exe=r"D:\Gry\SuperGra.exe", platform="Steam")
        self.assertEqual(g.stem, "supergra")


if __name__ == "__main__":
    unittest.main()
