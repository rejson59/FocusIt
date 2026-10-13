"""Testy v1.4: benchmark, klasyfikacja, rekomendacje, grafika UE, rejestr."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from focusit.core import (BenchmarkResult, apply_ue_settings, benchmark_cpu,
                          benchmark_ram, classify_device,
                          device_recommendations, graphics_recommendation,
                          parse_ini_sections, restore_ue_settings,
                          ue_current_settings, ue_recommended_changes)


class TestBenchmarkPieces(unittest.TestCase):
    def test_cpu_and_ram_benchmarks_return_positive(self):
        self.assertGreater(benchmark_cpu(duration=0.1, threads=1), 0)
        self.assertGreater(benchmark_ram(size_mb=16), 0)

    def test_classify(self):
        tier, score = classify_device(cpu_mbs=2000, ram_total_gb=32,
                                      gpu_vram_gb=16, disk_read_mbs=3000)
        self.assertEqual(tier, "Top")
        self.assertGreaterEqual(score, 90)
        tier2, score2 = classify_device(cpu_mbs=100, ram_total_gb=4,
                                        gpu_vram_gb=2, disk_read_mbs=80)
        self.assertEqual(tier2, "Słaby")
        self.assertLessEqual(score2, 25)


class TestRecommendations(unittest.TestCase):
    def test_graphics_by_vram(self):
        self.assertEqual(graphics_recommendation("Średni", 12)["Tekstury"], "Ultra")
        self.assertEqual(graphics_recommendation("Mocny", 8)["Tekstury"], "Wysokie")
        weak = graphics_recommendation("Słaby", 3)
        self.assertIn("1080p", weak["Rozdzielczość"])

    def test_device_recommendations_low_ram(self):
        r = BenchmarkResult(cpu_mbs=200, ram_total_gb=8, disk_read_mbs=100,
                            gpu_vram_gb=4, tier="Słaby", score=20)
        rec = device_recommendations(r)
        self.assertIn("Zamrażanie", rec["focusit"]["tryb_sesji"])
        self.assertTrue(any("HDD" in p for p in rec["porady"]))


SAMPLE_INI = """[/Script/FortniteGame.FortGameUserSettings]
ResolutionSizeX=1920

[ScalabilityGroups]
sg.ResolutionQuality=100.000000
sg.ShadowQuality=3
sg.TextureQuality=3

[/Script/Engine.GameUserSettings]
ResolutionSizeX=1920
ResolutionSizeY=1080
FullscreenMode=1
"""


class TestUnrealSettings(unittest.TestCase):
    def test_parse(self):
        sections = parse_ini_sections(SAMPLE_INI)
        self.assertEqual(sections["ScalabilityGroups"]["sg.ShadowQuality"], "3")

    def test_apply_and_restore(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "GameUserSettings.ini"
            path.write_text(SAMPLE_INI, encoding="utf-8")
            changes = ue_recommended_changes("Słaby", 4)
            self.assertEqual(changes["sg.ShadowQuality"], "0")
            msg = apply_ue_settings(path, changes)
            self.assertIn("Zapisano", msg)
            current = ue_current_settings(path)
            self.assertEqual(current["sg.ShadowQuality"], "0")
            self.assertEqual(current["ResolutionSizeX"], "1920")
            # kopia zapasowa istnieje i przywraca oryginał
            self.assertTrue(Path(str(path) + ".focusit.bak").exists())
            msg2 = restore_ue_settings(path)
            self.assertIn("Przywrócono", msg2)
            self.assertEqual(ue_current_settings(path)["sg.ShadowQuality"], "3")


class TestWindowsOnlyGuards(unittest.TestCase):
    def test_registry_helpers_safe_off_windows(self):
        from focusit.core import get_game_mode_state, set_game_gpu_preference
        if sys.platform.startswith("win"):
            self.skipTest("test tylko poza Windows")
        self.assertIsNone(get_game_mode_state())
        self.assertIn("tylko Windows", set_game_gpu_preference("C:\\gra.exe"))


if __name__ == "__main__":
    unittest.main()
