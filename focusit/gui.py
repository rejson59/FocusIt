"""FocusIt — interfejs graficzny (Tkinter, ciemny motyw gamingowy)."""

from __future__ import annotations

import copy
import json
import math
import threading
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import (SERVICE_CANDIDATES, BenchmarkResult, FocusSession,
                   FocusStore, GameEntry, ProcessInfo, apply_ue_settings,
                   check_for_update, compute_health_score, create_restore_point,
                   device_recommendations, execute_temp_clean, find_target_pid,
                   flush_dns, get_gpu_stats, get_system_stats, launch_app,
                   list_autostart, list_processes, parse_affinity,
                   preview_temp_clean, recover_previous_session,
                   restore_ue_settings, run_benchmark, scan_game_library,
                   set_autostart_enabled, set_game_gpu_preference,
                   ue_current_settings, ue_recommended_changes)

BG = "#060706"          # matowa czerń
PANEL = "#090B09"
CARD = "#10130E"
CARD_HOVER = "#182114"
TEXT = "#F2FFF5"
MUTED = "#8FA393"
ACCENT = "#00C853"      # neonowa zieleń — kolor marki
NEON = "#39FF14"        # jasny neon do poświat i ramek
CYAN = "#B7FF3C"        # limonka (drugi kolor wykresów)
GREEN = "#00E65A"       # start / gry
RED = "#FF3B30"
GOLD = "#FFC400"
BORDER = "#20331B"      # przygaszona zieleń ramek

_CLASSIC = {"BG": "#080A10", "PANEL": "#0F1420", "CARD": "#171E2E",
            "CARD_HOVER": "#212B42", "TEXT": "#EDF1F9", "MUTED": "#8A94A8",
            "ACCENT": "#8B5CF6", "NEON": "#8B5CF6", "CYAN": "#22D3EE",
            "GREEN": "#22C55E", "BORDER": "#232C42"}


def apply_theme(theme: str) -> None:
    """Ustawia paletę kolorów (neon = matowa czerń + zielone neony)."""
    global BG, PANEL, CARD, CARD_HOVER, TEXT, MUTED, ACCENT, NEON, CYAN, GREEN, BORDER
    if theme == "classic":
        vals = _CLASSIC
        BG, PANEL, CARD, CARD_HOVER, TEXT, MUTED = (vals["BG"], vals["PANEL"],
                                                    vals["CARD"], vals["CARD_HOVER"],
                                                    vals["TEXT"], vals["MUTED"])
        ACCENT, NEON, CYAN, GREEN, BORDER = (vals["ACCENT"], vals["NEON"],
                                             vals["CYAN"], vals["GREEN"],
                                             vals["BORDER"])
    else:
        BG, PANEL, CARD, CARD_HOVER, TEXT, MUTED = ("#060706", "#090B09",
                                                    "#10130E", "#182114",
                                                    "#F2FFF5", "#8FA393")
        ACCENT, NEON, CYAN, GREEN, BORDER = ("#00C853", "#39FF14", "#B7FF3C",
                                             "#00E65A", "#20331B")


def _hex_points(cx: float, cy: float, r: float) -> list[float]:
    pts: list[float] = []
    for i in range(6):
        ang = math.radians(60 * i)
        pts += [cx + r * math.cos(ang), cy + r * math.sin(ang)]
    return pts


def draw_honeycomb(canvas, w: int, h: int, r: int = 24,
                   bg: str = "#070806") -> None:
    """Matowe tło z plastrami miodu i rozproszoną neonową poświatą."""
    canvas.delete("all")
    canvas.create_rectangle(0, 0, w, h, fill=bg, outline="")
    dx, dy = r * 1.5, r * math.sqrt(3)
    col = 0
    x = -r
    while x < w + r:
        offset = (dy / 2) if col % 2 else 0
        row = 0
        y = -r + offset
        while y < h + r:
            glow = (col * 11 + row * 7) % 17 == 0
            pts = _hex_points(x, y, r - 2)
            if glow:
                canvas.create_polygon(_hex_points(x, y, r + 3), outline="#0E3D16",
                                      fill="", width=5)
                canvas.create_polygon(pts, outline=NEON, fill="#0B1A0C", width=2)
            else:
                canvas.create_polygon(pts, outline="#18301B", fill="", width=1)
            y += dy
            row += 1
        x += dx
        col += 1


def _lerp_color(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(a[i] + (b[i] - a[i]) * t):02x}" for i in range(3))

PAGES = [("panel", "🏠  Panel gry"), ("biblioteka", "🎮  Biblioteka gier"),
         ("presety", "🎯  Presety"),
         ("procesy", "🧹  Procesy i izolacja"), ("optymalizacja", "🚀  Optymalizacja"),
         ("sprzet", "🧪  Test sprzętu"),
         ("historia", "📊  Historia sesji"),
         ("ustawienia", "⚙️  Ustawienia")]


class FocusItApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.store = FocusStore()
        apply_theme(self.store.settings.get("theme", "neon"))
        self.session: FocusSession | None = None
        self.session_started = 0.0
        self.pomodoro_phase = "focus"
        self.pomodoro_left = 0
        self.cpu_hist: deque = deque([0.0] * 90, maxlen=90)
        self.ram_hist: deque = deque([0.0] * 90, maxlen=90)
        self.games: list[GameEntry] = []
        self.selected_game: GameEntry | None = None
        self.auto_started = False
        self._tick_count = 0
        self._gpu_cache: dict | None = None
        self._widget: tk.Toplevel | None = None
        self._cover_images: list = []
        self._overlays: dict[str, tk.Toplevel] = {}
        self._overlay_labels: dict[str, tk.Label] = {}
        self._overlays_for_session = False
        self.benchmark_result: BenchmarkResult | None = None

        from . import __version__
        root.title(f"FocusIt {__version__} — wyciśnij 100% ze swojego komputera")
        try:
            import sys as _sys
            base = Path(getattr(_sys, "_MEIPASS", Path(__file__).parent.parent))
            icon = base / "assets" / "focusit.ico"
            if icon.exists():
                root.iconbitmap(default=str(icon))
        except Exception:
            pass
        root.geometry("1200x780")
        root.minsize(1020, 660)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._style()
        self._build_layout()
        self._show_page("panel")
        self.refresh_targets()
        self.refresh_preset_lists()
        self.refresh_library()
        self.refresh_autostart()
        self.refresh_history()
        self._load_settings_to_ui()
        self._tick_stats()
        self.log("Witaj w FocusIt! Wybierz grę, preset i kliknij URUCHOM SESJĘ.")
        self.log("Domyślnie włączona jest SYMULACJA — program tylko pokaże, "
                 "co by zamknął, niczego nie zabijając. Odznacz ją, gdy będziesz gotowy.")
        self._recover_if_needed()
        self._maybe_onboard()
        self._hotkey_tick()
        if self.store.settings.get("check_updates", True):
            threading.Thread(target=self._check_update_bg, daemon=True).start()

    # ------------------------------------------------------- start programu
    def _recover_if_needed(self) -> None:
        if not self.store.load_session_state():
            return
        self.log("⚠ Wykryto przerwaną sesję (np. awaria programu) — przywracam stan…")
        try:
            for msg in recover_previous_session(self.store, log=self.log):
                self.log(f"Odzyskiwanie: {msg}")
        except Exception as exc:
            self.log(f"Odzyskiwanie nie powiodło się: {exc}")

    def _maybe_onboard(self) -> None:
        if self.store.settings.get("onboarded"):
            return
        self.store.settings["onboarded"] = True
        self.store.save()
        messagebox.showinfo(
            "Witaj w FocusIt! 🎮",
            "Jak zacząć w 30 sekund:\n\n"
            "1. Zakładka „Biblioteka gier” — kliknij swoją grę (albo wybierz ją "
            "z listy na Panelu).\n"
            "2. Kliknij „Podgląd planu”, żeby zobaczyć, co program zamknie, "
            "a co chroni.\n"
            "3. Na start zostaw włączoną SYMULACJĘ. Gdy plan wygląda dobrze, "
            "odznacz ją i kliknij URUCHOM SESJĘ.\n"
            "4. Po graniu: ZAKOŃCZ I PRZYWRÓĆ — wszystko wraca na miejsce.\n\n"
            "Skrót: Ctrl+Alt+F startuje/kończy sesję. Miłej gry!")

    def _check_update_bg(self) -> None:
        from . import __version__
        result = check_for_update(__version__)
        if result and result.get("is_newer"):
            self.root.after(0, lambda: self.log(
                f"⬆ Dostępna nowa wersja FocusIt: {result['latest']} "
                f"(masz {__version__}) — pobierz z zakładki Releases na GitHubie: "
                f"{result['url']}"))

    # ------------------------------------------------------------- skrót klaw.
    def _hotkey_tick(self) -> None:
        """Ctrl+Alt+F: start/stop sesji (Windows, bez dodatkowych bibliotek)."""
        try:
            if self.store.settings.get("hotkey_enabled", True):
                import ctypes
                user32 = ctypes.windll.user32  # type: ignore[attr-defined]
                pressed = (user32.GetAsyncKeyState(0x11) & 0x8000 and   # Ctrl
                           user32.GetAsyncKeyState(0x12) & 0x8000 and   # Alt
                           user32.GetAsyncKeyState(0x46) & 0x8000)      # F
                if pressed and not getattr(self, "_hk_prev", False):
                    if self.session and self.session.active:
                        self.log("Skrót Ctrl+Alt+F: kończę sesję.")
                        self.stop_session(silent=True)
                        messagebox.showinfo("FocusIt", "Sesja zakończona skrótem "
                                                       "Ctrl+Alt+F. Ustawienia przywrócone.")
                    elif self.selected_game or getattr(self, "_custom_exe", ""):
                        self.log("Skrót Ctrl+Alt+F: startuję sesję.")
                        self.start_session(from_auto=True)
                    else:
                        self.log("Skrót Ctrl+Alt+F: najpierw wybierz grę "
                                 "(Biblioteka albo Panel).")
                self._hk_prev = bool(pressed)
        except Exception:
            pass
        self.root.after(150, self._hotkey_tick)

    # ------------------------------------------------------------------ styl
    def _style(self) -> None:
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TCombobox", fieldbackground=CARD, background=CARD,
                    foreground=TEXT, arrowcolor=TEXT)
        s.configure("Treeview", background=CARD, fieldbackground=CARD,
                    foreground=TEXT, rowheight=24, font=("Segoe UI", 9))
        s.configure("Treeview.Heading", background=PANEL, foreground=TEXT,
                    font=("Segoe UI", 9, "bold"))
        s.map("Treeview", background=[("selected", ACCENT)])
        s.configure("TEntry", fieldbackground=CARD, foreground=TEXT)
        s.configure("TCheckbutton", background=BG, foreground=TEXT)
        s.configure("TRadiobutton", background=BG, foreground=TEXT)

    # ---------------------------------------------------------------- layout
    def _build_layout(self) -> None:
        sidebar = tk.Frame(self.root, bg=PANEL, width=225)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        from . import __version__
        self.version = __version__
        self.side_canvas = tk.Canvas(sidebar, bg=PANEL, height=104,
                                     highlightthickness=0)
        self.side_canvas.pack(fill="x")
        self.root.after(100, self._draw_sidebar)
        tk.Label(sidebar, text=f"wersja {__version__}  •  game bar", bg=PANEL,
                 fg=MUTED, font=("Segoe UI", 8)).pack(padx=18, pady=(0, 10),
                                                      anchor="w")

        self.nav_buttons: dict[str, tk.Button] = {}
        for key, label in PAGES:
            b = tk.Button(sidebar, text=label, anchor="w", relief="flat",
                          bg=PANEL, fg=TEXT, activebackground=CARD_HOVER,
                          activeforeground=TEXT, font=("Segoe UI", 11),
                          padx=16, pady=9, cursor="hand2",
                          command=lambda k=key: self._show_page(k))
            b.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = b

        self.side_status = tk.Label(sidebar, text="● Brak aktywnej sesji",
                                    bg=PANEL, fg=MUTED, font=("Segoe UI", 9),
                                    wraplength=190, justify="left")
        self.side_status.pack(side="bottom", pady=16, padx=14, anchor="w")

        self.container = tk.Frame(self.root, bg=BG)
        self.container.pack(side="right", fill="both", expand=True)

        self.frames: dict[str, tk.Frame] = {}
        for key, _ in PAGES:
            f = tk.Frame(self.container, bg=BG)
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.frames[key] = f

        self._build_panel_page(self.frames["panel"])
        self._build_library_page(self.frames["biblioteka"])
        self._build_presets_page(self.frames["presety"])
        self._build_processes_page(self.frames["procesy"])
        self._build_optimization_page(self.frames["optymalizacja"])
        self._build_benchmark_page(self.frames["sprzet"])
        self._build_history_page(self.frames["historia"])
        self._build_settings_page(self.frames["ustawienia"])

    def _show_page(self, key: str) -> None:
        self.frames[key].tkraise()
        for k, b in self.nav_buttons.items():
            b.configure(bg=ACCENT if k == key else PANEL)

    def _header(self, parent, title, subtitle=""):
        tk.Label(parent, text=title, bg=BG, fg=TEXT,
                 font=("Segoe UI", 17, "bold")).pack(padx=22, pady=(18, 0), anchor="w")
        if subtitle:
            tk.Label(parent, text=subtitle, bg=BG, fg=MUTED,
                     font=("Segoe UI", 9), wraplength=900,
                     justify="left").pack(padx=22, pady=(2, 8), anchor="w")

    # ------------------------------------------------------------- PANEL GRY
    def _build_panel_page(self, f: tk.Frame) -> None:
        # --- baner z gradientem ---
        self.banner = tk.Canvas(f, bg=BG, height=86, highlightthickness=0)
        self.banner.pack(fill="x", padx=22, pady=(14, 4))
        self.root.after(120, self._draw_banner)

        # --- statystyki ---
        stats = tk.Frame(f, bg=BG)
        stats.pack(fill="x", padx=22, pady=6)
        self.stat_labels: dict[str, tk.Label] = {}
        self.stat_bars: dict[str, tk.Canvas] = {}
        self._stat_pct: dict[str, float] = {}
        for key, title in [("cpu", "CPU"), ("ram", "RAM"), ("gpu", "GPU / temp."),
                           ("free", "Wolny RAM"), ("procs", "Procesy")]:
            card = tk.Frame(stats, bg=CARD, highlightthickness=1,
                            highlightbackground=BORDER)
            card.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(card, text=title, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(pady=(8, 0))
            lbl = tk.Label(card, text="—", bg=CARD, fg=TEXT,
                           font=("Segoe UI", 15, "bold"))
            lbl.pack(pady=(0, 1))
            bar = tk.Canvas(card, bg=CARD, height=5, highlightthickness=0)
            bar.pack(fill="x", padx=10, pady=(0, 9))
            self.stat_labels[key] = lbl
            self.stat_bars[key] = bar
            self._stat_pct[key] = 0.0

        # --- wykres na żywo + top procesów ---
        chart_box = tk.Frame(f, bg=CARD)
        chart_box.pack(fill="x", padx=22, pady=(2, 4))
        self.chart = tk.Canvas(chart_box, bg=CARD, height=86, highlightthickness=0)
        self.chart.pack(side="left", fill="x", expand=True)
        side = tk.Frame(chart_box, bg=CARD)
        side.pack(side="left", fill="y", padx=10, pady=6)
        tk.Label(side, text="■ CPU", bg=CARD, fg=NEON,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(side, text="■ RAM", bg=CARD, fg=CYAN,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.top_label = tk.Label(side, text="Top procesów: —", bg=CARD, fg=MUTED,
                                  font=("Segoe UI", 8), justify="left",
                                  wraplength=300)
        self.top_label.pack(anchor="w", pady=4)
        self.sug_label = tk.Label(side, text="", bg=CARD, fg=GOLD,
                                  font=("Segoe UI", 8), justify="left",
                                  wraplength=300)
        self.sug_label.pack(anchor="w")

        # --- cel ---
        box = tk.LabelFrame(f, text=" 1. Gra / program, na którym Ci zależy ",
                            bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"))
        box.pack(fill="x", padx=22, pady=8)
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x", padx=10, pady=8)
        self.target_combo = ttk.Combobox(row, state="readonly", width=62)
        self.target_combo.pack(side="left", fill="x", expand=True)
        tk.Button(row, text="↻ Odśwież listę", bg=CARD, fg=TEXT, relief="flat",
                  padx=10, pady=4, cursor="hand2",
                  command=self.refresh_targets).pack(side="left", padx=6)
        tk.Button(row, text="📂 Wybierz plik .exe…", bg=CARD, fg=TEXT,
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  command=self._browse_exe).pack(side="left")
        row2 = tk.Frame(box, bg=BG)
        row2.pack(fill="x", padx=10, pady=(0, 8))
        self.launch_target_var = tk.BooleanVar(value=False)
        tk.Checkbutton(row2, text="Uruchom tę grę/program przy starcie sesji",
                       variable=self.launch_target_var, bg=BG, fg=TEXT,
                       activebackground=BG, activeforeground=TEXT,
                       selectcolor=CARD).pack(side="left")
        self.target_info = tk.Label(row2, text="", bg=BG, fg=MUTED,
                                    font=("Segoe UI", 8))
        self.target_info.pack(side="left", padx=12)

        # --- preset + tryb ---
        box2 = tk.LabelFrame(f, text=" 2. Preset i tryb działania ",
                             bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"))
        box2.pack(fill="x", padx=22, pady=8)
        self.preset_var = tk.StringVar(value="Gry")
        self.preset_radios = tk.Frame(box2, bg=BG)
        self.preset_radios.pack(fill="x", padx=10, pady=6)
        self.preset_desc = tk.Label(box2, text="", bg=BG, fg=MUTED,
                                    font=("Segoe UI", 9), wraplength=850,
                                    justify="left")
        self.preset_desc.pack(padx=10, anchor="w")

        row3 = tk.Frame(box2, bg=BG)
        row3.pack(fill="x", padx=10, pady=6)
        tk.Label(row3, text="Tryb:", bg=BG, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.mode_var = tk.StringVar(value="preset")
        for val, txt in [("preset", "Zgodnie z presetem"),
                         ("gentle", "Łagodny (tylko lista presetu)"),
                         ("isolation", "☠ IZOLACJA — zabij wszystko niezwiązane z grą")]:
            tk.Radiobutton(row3, text=txt, value=val, variable=self.mode_var,
                           bg=BG, fg=TEXT, activebackground=BG,
                           activeforeground=TEXT, selectcolor=CARD,
                           font=("Segoe UI", 9)).pack(side="left", padx=8)
        row4 = tk.Frame(box2, bg=BG)
        row4.pack(fill="x", padx=10, pady=(0, 8))
        self.sim_var = tk.BooleanVar(
            value=self.store.settings.get("simulation_by_default", True))
        tk.Checkbutton(row4, text="SYMULACJA (podgląd — niczego nie zamykaj)",
                       variable=self.sim_var, bg=BG, fg=GOLD,
                       activebackground=BG, activeforeground=GOLD,
                       selectcolor=CARD, font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(row4, text="Odznacz dopiero, gdy plan wygląda dobrze.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=8)
        row5 = tk.Frame(box2, bg=BG)
        row5.pack(fill="x", padx=10, pady=(0, 8))
        self.freeze_var = tk.BooleanVar(value=False)
        tk.Checkbutton(row5, text="❄ Zamiast zabijać — ZAMRAŻAJ procesy (bezpieczniej: "
                                  "nic nie tracą, wracają po sesji)",
                       variable=self.freeze_var, bg=BG, fg=TEXT,
                       activebackground=BG, activeforeground=TEXT,
                       selectcolor=CARD, font=("Segoe UI", 9)).pack(side="left")

        # --- akcje ---
        actions = tk.Frame(f, bg=BG)
        actions.pack(fill="x", padx=22, pady=10)
        self.start_btn = tk.Button(
            actions, text="▶  URUCHOM SESJĘ FOCUS", bg=GREEN, fg="#06250F",
            font=("Segoe UI", 13, "bold"), relief="flat", padx=22, pady=10,
            cursor="hand2", command=self.start_session)
        self.start_btn.pack(side="left")
        self.stop_btn = tk.Button(
            actions, text="■  ZAKOŃCZ I PRZYWRÓĆ", bg=RED, fg="white",
            font=("Segoe UI", 13, "bold"), relief="flat", padx=22, pady=10,
            cursor="hand2", command=self.stop_session, state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        tk.Button(actions, text="👁 Podgląd planu", bg=CARD, fg=TEXT,
                  font=("Segoe UI", 11), relief="flat", padx=16, pady=10,
                  cursor="hand2", command=self.preview_plan).pack(side="left")
        self.session_label = tk.Label(actions, text="", bg=BG, fg=GOLD,
                                      font=("Segoe UI", 11, "bold"))
        self.session_label.pack(side="left", padx=14)

        # --- nakładka w grze ---
        ov = tk.LabelFrame(f, text=" Nakładka w grze (półprzezroczyste widżety) ",
                           bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"))
        ov.pack(fill="x", padx=22, pady=(0, 8))
        ovrow = tk.Frame(ov, bg=BG)
        ovrow.pack(fill="x", padx=10, pady=6)
        self.ov_vars: dict[str, tk.BooleanVar] = {}
        chosen_widgets = set(self.store.settings.get(
            "overlay_widgets", ["czas", "statystyki", "przyciski"]))
        for key, label in [("czas", "⏱ Czas sesji"),
                           ("statystyki", "📊 CPU/RAM/GPU"),
                           ("przyciski", "🎛 Przyciski akcji")]:
            var = tk.BooleanVar(value=key in chosen_widgets)
            self.ov_vars[key] = var
            tk.Checkbutton(ovrow, text=label, variable=var, bg=BG, fg=TEXT,
                           activebackground=BG, activeforeground=TEXT,
                           selectcolor=CARD, font=("Segoe UI", 9),
                           command=self._save_overlay_choices).pack(side="left",
                                                                    padx=4)
        tk.Label(ovrow, text="Przezroczystość:", bg=BG, fg=TEXT,
                 font=("Segoe UI", 9)).pack(side="left", padx=(14, 2))
        self.ov_opacity = tk.IntVar(
            value=int(self.store.settings.get("overlay_opacity", 85)))
        tk.Scale(ovrow, from_=40, to=100, orient="horizontal",
                 variable=self.ov_opacity, bg=BG, fg=TEXT, length=110,
                 highlightthickness=0, troughcolor=CARD,
                 command=lambda _v: self._save_overlay_choices()).pack(side="left")
        self.ov_edit = tk.BooleanVar(value=False)
        tk.Checkbutton(ovrow, text="✥ Tryb edycji (przeciąganie)",
                       variable=self.ov_edit, bg=BG, fg=GOLD,
                       activebackground=BG, activeforeground=GOLD,
                       selectcolor=CARD, font=("Segoe UI", 9),
                       command=self._overlay_edit_toggled).pack(side="left", padx=10)
        tk.Button(ovrow, text="👁 Pokaż/ukryj nakładkę", bg=CARD, fg=TEXT,
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  command=self._toggle_overlays_preview).pack(side="left")

        # --- log ---
        tk.Label(f, text="Dziennik sesji:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(padx=24, anchor="w")
        self.log_box = tk.Text(f, bg=CARD, fg=TEXT, height=9, relief="flat",
                               font=("Consolas", 9), wrap="word",
                               insertbackground=TEXT)
        self.log_box.pack(fill="both", expand=True, padx=22, pady=(2, 16))

    # ------------------------------------------------------------ BIBLIOTEKA
    def _build_library_page(self, f: tk.Frame) -> None:
        self._header(f, "🎮 Biblioteka gier",
                     "FocusIt wykrywa gry ze Steam, Epic i GOG. Kliknij grę, aby "
                     "ustawić ją jako cel sesji. Każda gra może mieć własny profil "
                     "(co zachować / co zamykać).")
        bar = tk.Frame(f, bg=BG)
        bar.pack(fill="x", padx=22, pady=4)
        tk.Button(bar, text="↻ Skanuj dysk (Steam/Epic/GOG)", bg=ACCENT,
                  fg="#03150A", relief="flat", padx=14, pady=6, cursor="hand2",
                  font=("Segoe UI", 10, "bold"),
                  command=self.refresh_library).pack(side="left")
        tk.Button(bar, text="📂 Dodaj grę ręcznie…", bg=CARD, fg=TEXT,
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._add_game_manually).pack(side="left", padx=6)
        tk.Button(bar, text="✏ Edytuj profil wybranej gry", bg=CARD, fg=TEXT,
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._edit_game_profile).pack(side="left", padx=2)
        self.library_info = tk.Label(bar, text="", bg=BG, fg=MUTED,
                                     font=("Segoe UI", 9))
        self.library_info.pack(side="left", padx=12)

        wrap = tk.Frame(f, bg=BG)
        wrap.pack(fill="both", expand=True, padx=22, pady=8)
        self.lib_canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(wrap, orient="vertical",
                               command=self.lib_canvas.yview)
        self.lib_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.lib_canvas.pack(side="left", fill="both", expand=True)
        self.lib_frame = tk.Frame(self.lib_canvas, bg=BG)
        self.lib_canvas.create_window((0, 0), window=self.lib_frame, anchor="nw")
        self.lib_frame.bind(
            "<Configure>", lambda _e: self.lib_canvas.configure(
                scrollregion=self.lib_canvas.bbox("all")))

    def refresh_library(self) -> None:
        self.games = scan_game_library()
        # gry dodane ręcznie (zapisane w profilach, a niewykryte na dysku)
        known = {g.exe.lower() for g in self.games if g.exe}
        for exe, prof in self.store.game_profiles.items():
            if exe and exe not in known and Path(exe).exists():
                self.games.append(GameEntry(
                    name=prof.get("display_name") or Path(exe).stem,
                    exe=exe, platform="Ręcznie"))
        for w in self.lib_frame.winfo_children():
            w.destroy()
        self._cover_images = []
        if not self.games:
            tk.Label(self.lib_frame,
                     text="Nie wykryto gier. Zainstaluj grę przez Steam/Epic "
                          "albo dodaj ją ręcznie przyciskiem powyżej.",
                     bg=BG, fg=MUTED, font=("Segoe UI", 11),
                     wraplength=700, justify="left").pack(padx=8, pady=12, anchor="w")
        cols = 4
        self._tile_frames: dict[str, tk.Frame] = {}
        for i, game in enumerate(self.games):
            tile = tk.Frame(self.lib_frame, bg=CARD, highlightthickness=2,
                            highlightbackground=BORDER)
            tile.grid(row=i // cols, column=i % cols, padx=6, pady=6, sticky="nsew")
            self._tile_frames[game.exe.lower()] = tile

            def hover(_e, t=tile):
                t.configure(highlightbackground=CYAN)

            def unhover(_e, t=tile, g=game):
                sel = self.selected_game and \
                    self.selected_game.exe.lower() == g.exe.lower()
                t.configure(highlightbackground=ACCENT if sel else BORDER)

            tile.bind("<Enter>", hover)
            tile.bind("<Leave>", unhover)
            img = self._cover_for(game)
            btn = tk.Button(tile, image=img if img else None,
                            text="" if img else f"🎮\n{game.name}",
                            bg=CARD, fg=TEXT, relief="flat", cursor="hand2",
                            font=("Segoe UI", 10, "bold"), width=20, height=5 if not img else 0,
                            command=lambda g=game: self._select_game(g))
            btn.pack(fill="x")
            tk.Label(tile, text=game.name, bg=CARD, fg=TEXT,
                     font=("Segoe UI", 9, "bold"), wraplength=190).pack(padx=6)
            tk.Label(tile, text=f"{game.platform}"
                             + ("  •  ma własny profil" if self.store.game_profile(game.exe) else ""),
                     bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(padx=6, pady=(0, 6))
        self.library_info.configure(text=f"Wykryto gier: {len(self.games)}")
        self.log(f"Biblioteka gier: znaleziono {len(self.games)} tytułów.")

    def _cover_for(self, game: GameEntry):
        if not game.image or not Path(game.image).exists():
            return None
        try:
            from PIL import Image, ImageTk
            img = Image.open(game.image)
            img.thumbnail((170, 240))
            photo = ImageTk.PhotoImage(img)
            self._cover_images.append(photo)
            return photo
        except Exception:
            return None

    def _select_game(self, game: GameEntry) -> None:
        self.selected_game = game
        for key, tile in getattr(self, "_tile_frames", {}).items():
            tile.configure(highlightbackground=ACCENT
                           if key == game.exe.lower() else BORDER)
        if game.exe:
            self._custom_exe = game.exe
            self.target_combo.set(Path(game.exe).name)
            self.target_info.configure(text=game.exe)
        self.preset_var.set("Gry")
        self._preset_changed()
        self._show_page("panel")
        prof = self.store.game_profile(game.exe)
        self.log(f"Wybrano grę: {game.name} ({game.platform})"
                 + (" — zastosowano jej własny profil." if prof else "."))
        self.log("Możesz od razu kliknąć URUCHOM SESJĘ albo podejrzeć plan.")

    def _add_game_manually(self) -> None:
        path = filedialog.askopenfilename(
            title="Wskaż plik .exe gry",
            filetypes=[("Programy", "*.exe"), ("Wszystkie pliki", "*.*")])
        if not path:
            return
        game = GameEntry(name=Path(path).stem, exe=path, platform="Ręcznie")
        self.store.set_game_profile(path, {"display_name": game.name})
        self.games.append(game)
        self.refresh_library()
        self._select_game(game)

    def _edit_game_profile(self) -> None:
        game = self.selected_game
        if not game or not game.exe:
            messagebox.showinfo("FocusIt", "Najpierw kliknij grę w bibliotece "
                                           "albo dodaj ją ręcznie.")
            return
        prof = self.store.game_profile(game.exe)
        win = tk.Toplevel(self.root)
        win.title(f"Profil gry: {game.name}")
        win.configure(bg=BG)
        win.geometry("520x300")
        tk.Label(win, text=f"🎮 {game.name}", bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(padx=16, pady=12, anchor="w")
        fields = {}
        for key, label in [("keep_apps", "Zawsze zachowaj przy tej grze:"),
                           ("close_apps", "Dodatkowo zamykaj przy tej grze:")]:
            tk.Label(win, text=label + " (po przecinku, np. discord.exe, obs64.exe)",
                     bg=BG, fg=TEXT, font=("Segoe UI", 9)).pack(padx=16, anchor="w")
            var = tk.StringVar(value=", ".join(prof.get(key, [])))
            tk.Entry(win, textvariable=var, bg=CARD, fg=TEXT, relief="flat",
                     font=("Segoe UI", 10), insertbackground=TEXT).pack(
                         fill="x", padx=16, pady=4)
            fields[key] = var
        tk.Label(win, text="Tryb sesji dla tej gry:", bg=BG, fg=TEXT,
                 font=("Segoe UI", 9)).pack(padx=16, anchor="w", pady=(8, 0))
        mode_var = tk.StringVar(value=prof.get("mode", "isolation"))
        mrow = tk.Frame(win, bg=BG)
        mrow.pack(padx=16, anchor="w")
        for val, txt in [("isolation", "Izolacja"), ("gentle", "Łagodny")]:
            tk.Radiobutton(mrow, text=txt, value=val, variable=mode_var,
                           bg=BG, fg=TEXT, activebackground=BG,
                           selectcolor=CARD).pack(side="left", padx=6)
        tk.Label(win, text="Rdzenie CPU dla gry (opcjonalnie, np. 0-7; "
                           "puste = wszystkie):", bg=BG, fg=TEXT,
                 font=("Segoe UI", 9)).pack(padx=16, anchor="w", pady=(8, 0))
        affinity_var = tk.StringVar(value=prof.get("affinity", ""))
        tk.Entry(win, textvariable=affinity_var, bg=CARD, fg=TEXT, relief="flat",
                 font=("Segoe UI", 10), insertbackground=TEXT).pack(
                     fill="x", padx=16, pady=4)

        def save() -> None:
            new_prof = dict(prof)
            new_prof.update({
                "display_name": game.name,
                "keep_apps": self._split(fields["keep_apps"].get()),
                "close_apps": self._split(fields["close_apps"].get()),
                "mode": mode_var.get(),
                "affinity": affinity_var.get().strip(),
            })
            self.store.set_game_profile(game.exe, new_prof)
            self.log(f"Zapisano profil gry „{game.name}”.")
            self.refresh_library()
            win.destroy()

        tk.Button(win, text="💾 Zapisz profil", bg=ACCENT, fg="#03150A",
                  font=("Segoe UI", 11, "bold"), relief="flat", padx=16, pady=6,
                  cursor="hand2", command=save).pack(padx=16, pady=14, anchor="w")

    # ---------------------------------------------------------- OPTYMALIZACJA
    def _build_optimization_page(self, f: tk.Frame) -> None:
        self._header(f, "🚀 Optymalizacja komputera",
                     "Dodatkowe, bezpieczne porządki. Wszystko z podglądem "
                     "przed wykonaniem i wszystko odwracalne.")
        # kondycja PC
        hbox = tk.LabelFrame(f, text=" Wynik kondycji PC ", bg=BG, fg=ACCENT,
                             font=("Segoe UI", 10, "bold"))
        hbox.pack(fill="x", padx=22, pady=8)
        hrow = tk.Frame(hbox, bg=BG)
        hrow.pack(fill="x", padx=12, pady=8)
        self.health_score_label = tk.Label(hrow, text="—", bg=BG, fg=GREEN,
                                           font=("Segoe UI", 30, "bold"))
        self.health_score_label.pack(side="left")
        self.health_tips = tk.Label(hrow, text="Kliknij „Przeanalizuj”, aby "
                                               "ocenić kondycję komputera.",
                                    bg=BG, fg=TEXT, font=("Segoe UI", 9),
                                    justify="left", wraplength=640)
        self.health_tips.pack(side="left", padx=14)
        tk.Button(hrow, text="🔎 Przeanalizuj", bg=ACCENT, fg="#03150A",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  font=("Segoe UI", 10, "bold"),
                  command=self._analyze_health).pack(side="right")
        # usługi na czas sesji + DNS
        sbox = tk.LabelFrame(f, text=" Na czas sesji gry (Windows, wymaga administratora) ",
                             bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"))
        sbox.pack(fill="x", padx=22, pady=8)
        tk.Label(sbox, text="Wstrzymaj te usługi podczas sesji — same wrócą "
                            "po jej zakończeniu:", bg=BG, fg=TEXT,
                 font=("Segoe UI", 9)).pack(padx=12, pady=(8, 2), anchor="w")
        self.service_vars: dict[str, tk.BooleanVar] = {}
        chosen = set(self.store.settings.get("stop_services", []))
        for name, desc in SERVICE_CANDIDATES.items():
            var = tk.BooleanVar(value=name in chosen)
            self.service_vars[name] = var
            tk.Checkbutton(sbox, text=f"{desc} ({name})", variable=var,
                           bg=BG, fg=TEXT, activebackground=BG,
                           activeforeground=TEXT, selectcolor=CARD,
                           command=self._save_service_choices).pack(
                               padx=20, anchor="w")
        tk.Button(sbox, text="🌐 Wyczyść pamięć podręczną DNS (ping)",
                  bg=CARD, fg=TEXT, relief="flat", padx=14, pady=5,
                  cursor="hand2",
                  command=lambda: messagebox.showinfo("FocusIt", flush_dns(self.log))
                  ).pack(padx=12, pady=8, anchor="w")

        dbox = tk.LabelFrame(f, text=" Głębokie ustawienia systemowe (odwracalne) ",
                             bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"))
        dbox.pack(fill="x", padx=22, pady=8)
        self.deep_gamemode = tk.BooleanVar(
            value=self.store.settings.get("windows_game_mode_session", False))
        tk.Checkbutton(dbox, text="Włączaj Tryb gry Windows na czas sesji "
                                  "(po sesji wraca poprzedni stan)",
                       variable=self.deep_gamemode, bg=BG, fg=TEXT,
                       activebackground=BG, activeforeground=TEXT,
                       selectcolor=CARD, font=("Segoe UI", 9),
                       command=self._save_deep_settings).pack(padx=12, pady=(8, 2),
                                                              anchor="w")
        grow2 = tk.Frame(dbox, bg=BG)
        grow2.pack(padx=12, pady=6, anchor="w")
        tk.Button(grow2, text="🎮 Ustaw 'Wysoka wydajność' GPU dla wybranej gry",
                  bg=CARD, fg=TEXT, relief="flat", padx=12, pady=5,
                  cursor="hand2", command=self._gpu_pref_on).pack(side="left")
        tk.Button(grow2, text="↩ Usuń preferencję GPU", bg=CARD, fg=TEXT,
                  relief="flat", padx=12, pady=5, cursor="hand2",
                  command=self._gpu_pref_off).pack(side="left", padx=6)
        tk.Label(dbox, text="FocusIt świadomie NIE stosuje popularnych „magicznych” "
                            "tweaków (HPET, timer resolution, losowe wpisy rejestru) "
                            "— nie ma dowodów, że pomagają, a potrafią szkodzić. "
                            "Robimy tylko rzeczy mierzalne i odwracalne.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=820,
                 justify="left").pack(padx=12, pady=(2, 8), anchor="w")
        # pliki tymczasowe
        box = tk.LabelFrame(f, text=" Pliki tymczasowe (folder Temp użytkownika) ",
                            bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"))
        box.pack(fill="x", padx=22, pady=8)
        self.temp_label = tk.Label(box, text="Kliknij „Skanuj”, aby zobaczyć, "
                                             "ile śmieci można usunąć (pliki starsze niż 24 h).",
                                   bg=BG, fg=TEXT, font=("Segoe UI", 9))
        self.temp_label.pack(padx=12, pady=8, anchor="w")
        row = tk.Frame(box, bg=BG)
        row.pack(padx=12, pady=(0, 10), anchor="w")
        tk.Button(row, text="🔍 Skanuj", bg=CARD, fg=TEXT, relief="flat",
                  padx=14, pady=5, cursor="hand2",
                  command=self._scan_temp).pack(side="left")
        tk.Button(row, text="🧹 Czyść starsze niż 24 h", bg=RED, fg="white",
                  relief="flat", padx=14, pady=5, cursor="hand2",
                  command=self._clean_temp).pack(side="left", padx=8)

        # punkt przywracania
        box2 = tk.LabelFrame(f, text=" Bezpieczeństwo ", bg=BG, fg=ACCENT,
                             font=("Segoe UI", 10, "bold"))
        box2.pack(fill="x", padx=22, pady=8)
        tk.Label(box2, text="Zalecane przed pierwszą sesją izolacji na żywo:",
                 bg=BG, fg=TEXT, font=("Segoe UI", 9)).pack(padx=12, pady=(8, 2),
                                                            anchor="w")
        tk.Button(box2, text="🛡 Utwórz punkt przywracania systemu (Windows)",
                  bg=CARD, fg=TEXT, relief="flat", padx=14, pady=5,
                  cursor="hand2", command=self._restore_point).pack(
                      padx=12, pady=(0, 10), anchor="w")

        # autostart
        box3 = tk.LabelFrame(f, text=" Programy startujące z Windowsem (autostart) ",
                             bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"))
        box3.pack(fill="both", expand=True, padx=22, pady=8)
        cols = ("nazwa", "polecenie", "zrodlo")
        self.auto_tree = ttk.Treeview(box3, columns=cols, show="headings", height=9)
        for col, txt, w in [("nazwa", "Program", 220),
                            ("polecenie", "Polecenie", 560),
                            ("zrodlo", "Źródło", 90)]:
            self.auto_tree.heading(col, text=txt)
            self.auto_tree.column(col, width=w)
        self.auto_tree.pack(fill="both", expand=True, padx=10, pady=8)
        row3 = tk.Frame(box3, bg=BG)
        row3.pack(padx=10, pady=(0, 10), anchor="w")
        tk.Button(row3, text="↻ Odśwież", bg=CARD, fg=TEXT, relief="flat",
                  padx=14, pady=5, cursor="hand2",
                  command=self.refresh_autostart).pack(side="left")
        tk.Button(row3, text="⏸ Wyłącz zaznaczony (odwracalne)", bg=CARD,
                  fg=TEXT, relief="flat", padx=14, pady=5, cursor="hand2",
                  command=self._disable_autostart).pack(side="left", padx=8)
        tk.Button(row3, text="▶ Przywróć wyłączone", bg=CARD, fg=TEXT,
                  relief="flat", padx=14, pady=5, cursor="hand2",
                  command=self._restore_autostart).pack(side="left")

        # eksport / import presetów
        box4 = tk.LabelFrame(f, text=" Presety — kopie i udostępnianie ",
                             bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"))
        box4.pack(fill="x", padx=22, pady=8)
        row4 = tk.Frame(box4, bg=BG)
        row4.pack(padx=12, pady=10, anchor="w")
        tk.Button(row4, text="📤 Eksportuj presety do pliku…", bg=CARD, fg=TEXT,
                  relief="flat", padx=14, pady=5, cursor="hand2",
                  command=self._export_presets).pack(side="left")
        tk.Button(row4, text="📥 Importuj presety z pliku…", bg=CARD, fg=TEXT,
                  relief="flat", padx=14, pady=5, cursor="hand2",
                  command=self._import_presets).pack(side="left", padx=8)

    def _save_deep_settings(self) -> None:
        self.store.settings["windows_game_mode_session"] = self.deep_gamemode.get()
        self.store.save()
        self.log("Zapisano głębokie ustawienia systemowe.")

    def _gpu_pref_on(self) -> None:
        _, exe, _ = self._resolve_target()
        msg = set_game_gpu_preference(exe, True)
        self.log(msg)
        messagebox.showinfo("FocusIt", msg)

    def _gpu_pref_off(self) -> None:
        _, exe, _ = self._resolve_target()
        msg = set_game_gpu_preference(exe, False)
        self.log(msg)
        messagebox.showinfo("FocusIt", msg)

    def _save_service_choices(self) -> None:
        self.store.settings["stop_services"] = [
            name for name, var in self.service_vars.items() if var.get()]
        self.store.save()
        self.log("Zapisano wybór usług wstrzymywanych na czas sesji.")

    def _analyze_health(self) -> None:
        stats = get_system_stats()
        temp = preview_temp_clean()
        autostart = len(list_autostart())
        heavy = [p for p in list_processes()
                 if p.exe and p.memory_mb > 300][:6]
        score, tips = compute_health_score(stats, temp, autostart, heavy)
        color = GREEN if score >= 75 else (GOLD if score >= 50 else RED)
        self.health_score_label.configure(text=f"{score}", fg=color)
        self.health_tips.configure(text="• " + "\n• ".join(tips))
        self.log(f"Wynik kondycji PC: {score}/100.")

    def _scan_temp(self) -> None:
        r = preview_temp_clean()
        self.temp_label.configure(
            text=f"Do usunięcia: {r['files']} plików "
                 f"({r['size_mb']:.1f} MB) starszych niż {r['older_than_hours']} h.")
        self.log(f"Skan Temp: {r['files']} plików, {r['size_mb']:.1f} MB.")

    def _clean_temp(self) -> None:
        r = preview_temp_clean()
        if r["files"] == 0:
            messagebox.showinfo("FocusIt", "Brak starych plików tymczasowych. Czysto!")
            return
        if not messagebox.askyesno(
                "FocusIt", f"Usunąć {r['files']} plików tymczasowych "
                           f"({r['size_mb']:.1f} MB)?\nTylko pliki starsze niż 24 h "
                           "z Twojego folderu Temp. Używane pliki zostaną pominięte."):
            return
        result = execute_temp_clean()
        self._scan_temp()
        self.log(f"Wyczyszczono Temp: {result['removed']} plików, "
                 f"{result['freed_mb']:.1f} MB (pominięte: {result['failed']}).")
        messagebox.showinfo("FocusIt", f"Usunięto {result['removed']} plików "
                                       f"({result['freed_mb']:.1f} MB).")

    def _restore_point(self) -> None:
        self.log("Tworzę punkt przywracania (może potrwać)…")
        self.root.update()
        msg = create_restore_point()
        self.log(msg)
        messagebox.showinfo("FocusIt", msg)

    def refresh_autostart(self) -> None:
        self._auto_entries = list_autostart()
        for item in self.auto_tree.get_children():
            self.auto_tree.delete(item)
        for e in self._auto_entries:
            self.auto_tree.insert("", "end", values=(e["name"], e["command"], e["hive"]))
        disabled = self.store.settings.get("autostart_backup", {})
        for name in disabled:
            self.auto_tree.insert("", "end", values=(
                f"{name}  (wyłączony przez FocusIt)", disabled[name].get("command", ""), "—"))

    def _disable_autostart(self) -> None:
        sel = self.auto_tree.selection()
        if not sel:
            messagebox.showinfo("FocusIt", "Zaznacz program na liście.")
            return
        name = str(self.auto_tree.item(sel[0])["values"][0])
        entry = next((e for e in getattr(self, "_auto_entries", [])
                      if e["name"] == name), None)
        if not entry:
            return
        if set_autostart_enabled(entry, enabled=False):
            backup = self.store.settings.setdefault("autostart_backup", {})
            backup[entry["name"]] = entry
            self.store.save()
            self.log(f"Wyłączono autostart: {entry['name']} (kopia zapasowa zapisana).")
            self.refresh_autostart()
        else:
            messagebox.showwarning("FocusIt", "Nie udało się wyłączyć wpisu "
                                              "(wpisy HKLM wymagają administratora).")

    def _restore_autostart(self) -> None:
        backup = self.store.settings.get("autostart_backup", {})
        if not backup:
            messagebox.showinfo("FocusIt", "Brak wyłączonych wpisów do przywrócenia.")
            return
        done = 0
        for name, entry in list(backup.items()):
            if set_autostart_enabled(entry, enabled=True):
                done += 1
                del backup[name]
        self.store.save()
        self.refresh_autostart()
        self.log(f"Przywrócono autostart dla {done} programów.")

    def _export_presets(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Eksport presetów", defaultextension=".json",
            filetypes=[("JSON", "*.json")])
        if path:
            Path(path).write_text(json.dumps(
                {"presets": self.store.presets,
                 "game_profiles": self.store.game_profiles},
                ensure_ascii=False, indent=2), encoding="utf-8")
            self.log(f"Wyeksportowano presety do: {path}")

    def _import_presets(self) -> None:
        path = filedialog.askopenfilename(
            title="Import presetów", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            count = 0
            for preset in data.get("presets", []):
                if preset.get("name"):
                    preset["built_in"] = False
                    self.store.upsert_preset(preset)
                    count += 1
            for exe, prof in data.get("game_profiles", {}).items():
                self.store.game_profiles[exe] = prof
            self.store.save()
            self.refresh_preset_lists()
            self.refresh_library()
            self.log(f"Zaimportowano {count} presetów z pliku {path}.")
        except Exception as exc:
            messagebox.showwarning("FocusIt", f"Nie udało się importować: {exc}")

    # ---------------------------------------------------------------- PRESETY
    def _build_presets_page(self, f: tk.Frame) -> None:
        self._header(f, "🎯 Presety",
                     "Gotowe presety możesz edytować po utworzeniu ich kopii. "
                     "Własne presety dodawaj przyciskiem „Nowy”. "
                     "Aplikacje wpisuj po przecinku, np.: chrome.exe, spotify.exe")
        body = tk.Frame(f, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=8)

        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y")
        self.preset_list = tk.Listbox(left, bg=CARD, fg=TEXT, width=26,
                                      relief="flat", font=("Segoe UI", 11),
                                      selectbackground=ACCENT, height=16)
        self.preset_list.pack(fill="y", expand=True)
        self.preset_list.bind("<<ListboxSelect>>", self._preset_selected)
        btns = tk.Frame(left, bg=BG)
        btns.pack(fill="x", pady=6)
        tk.Button(btns, text="＋ Nowy", bg=CARD, fg=TEXT, relief="flat",
                  cursor="hand2", command=self._new_preset).pack(side="left", padx=2)
        tk.Button(btns, text="⧉ Kopia", bg=CARD, fg=TEXT, relief="flat",
                  cursor="hand2", command=self._copy_preset).pack(side="left", padx=2)
        tk.Button(btns, text="🗑 Usuń", bg=CARD, fg=RED, relief="flat",
                  cursor="hand2", command=self._delete_preset).pack(side="left", padx=2)

        form = tk.Frame(body, bg=BG)
        form.pack(side="left", fill="both", expand=True, padx=18)
        self.p_fields: dict[str, tk.Variable] = {}
        rows = [
            ("name", "Nazwa presetu:"), ("icon", "Ikona (emoji):"),
            ("description", "Opis:"), ("close_apps", "Zamykaj te aplikacje:"),
            ("launch_apps", "Uruchamiaj przy starcie (ścieżki/nazwy):"),
            ("keep_apps", "Zawsze zachowaj przy tym presecie:"),
        ]
        for i, (key, label) in enumerate(rows):
            tk.Label(form, text=label, bg=BG, fg=TEXT,
                     font=("Segoe UI", 9)).grid(row=i, column=0, sticky="w", pady=4)
            var = tk.StringVar()
            tk.Entry(form, textvariable=var, bg=CARD, fg=TEXT, relief="flat",
                     font=("Segoe UI", 10), width=58,
                     insertbackground=TEXT).grid(row=i, column=1, sticky="ew", pady=4)
            self.p_fields[key] = var
        r = len(rows)
        tk.Label(form, text="Tryb:", bg=BG, fg=TEXT).grid(row=r, column=0, sticky="w")
        self.p_mode = tk.StringVar(value="gentle")
        mrow = tk.Frame(form, bg=BG)
        mrow.grid(row=r, column=1, sticky="w")
        for val, txt in [("gentle", "Łagodny"), ("isolation", "Izolacja (agresywny)")]:
            tk.Radiobutton(mrow, text=txt, value=val, variable=self.p_mode,
                           bg=BG, fg=TEXT, activebackground=BG,
                           selectcolor=CARD).pack(side="left", padx=6)
        r += 1
        self.p_power = tk.BooleanVar()
        self.p_priority = tk.BooleanVar()
        tk.Checkbutton(form, text="Plan zasilania: Wysoka wydajność (Windows)",
                       variable=self.p_power, bg=BG, fg=TEXT,
                       activebackground=BG, selectcolor=CARD).grid(
                           row=r, column=1, sticky="w")
        r += 1
        tk.Checkbutton(form, text="Wysoki priorytet procesu gry/programu",
                       variable=self.p_priority, bg=BG, fg=TEXT,
                       activebackground=BG, selectcolor=CARD).grid(
                           row=r, column=1, sticky="w")
        r += 1
        tk.Label(form, text="Timer Pomodoro (min, 0 = wyłączony):",
                 bg=BG, fg=TEXT).grid(row=r, column=0, sticky="w")
        self.p_pomodoro = tk.StringVar(value="0")
        tk.Entry(form, textvariable=self.p_pomodoro, bg=CARD, fg=TEXT,
                 relief="flat", width=10, insertbackground=TEXT).grid(
                     row=r, column=1, sticky="w")
        r += 1
        tk.Button(form, text="💾 Zapisz preset", bg=ACCENT, fg="#03150A",
                  font=("Segoe UI", 11, "bold"), relief="flat", padx=18, pady=7,
                  cursor="hand2", command=self._save_preset).grid(
                      row=r, column=1, sticky="w", pady=12)
        form.columnconfigure(1, weight=1)

    # ---------------------------------------------------------------- PROCESY
    def _build_processes_page(self, f: tk.Frame) -> None:
        self._header(f, "🧹 Procesy i tryb izolacji",
                     "Tu zobaczysz dokładny plan: co FocusIt zamknie, a co zachowa "
                     "i dlaczego. Procesy systemowe są zawsze chronione. "
                     "Dwuklik na proces doda go do listy „Zachowaj”.")
        bar = tk.Frame(f, bg=BG)
        bar.pack(fill="x", padx=22, pady=4)
        tk.Button(bar, text="👁 Oblicz plan dla wybranej gry", bg=ACCENT,
                  fg="#03150A", relief="flat", padx=14, pady=6, cursor="hand2",
                  font=("Segoe UI", 10, "bold"),
                  command=self.preview_plan).pack(side="left")
        tk.Label(bar, text="Szukaj:", bg=BG, fg=TEXT).pack(side="left", padx=(16, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter_tree())
        tk.Entry(bar, textvariable=self.search_var, bg=CARD, fg=TEXT,
                 relief="flat", width=26, insertbackground=TEXT).pack(side="left")
        self.plan_summary = tk.Label(bar, text="", bg=BG, fg=GOLD,
                                     font=("Segoe UI", 10, "bold"))
        self.plan_summary.pack(side="left", padx=14)

        cols = ("decyzja", "pid", "nazwa", "ram", "powod", "sciezka")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=22)
        for col, txt, w in [("decyzja", "Decyzja", 110), ("pid", "PID", 70),
                            ("nazwa", "Proces", 210), ("ram", "RAM (MB)", 90),
                            ("powod", "Powód", 330), ("sciezka", "Ścieżka", 340)]:
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor="w")
        self.tree.tag_configure("kill", foreground="#FF8A8A")
        self.tree.tag_configure("keep", foreground=MUTED)
        self.tree.pack(fill="both", expand=True, padx=22, pady=8)
        self.tree.bind("<Double-1>", self._tree_double_click)
        self._tree_rows: list[tuple] = []

    # ------------------------------------------------------------ TEST SPRZĘTU
    def _build_benchmark_page(self, f: tk.Frame) -> None:
        self._header(f, "🧪 Test możliwości urządzenia",
                     "FocusIt zmierzy CPU, RAM, dysk i GPU, oceni klasę sprzętu "
                     "i sam zaproponuje najlepsze ustawienia — dla programu "
                     "i dla grafiki w grach.")
        bar = tk.Frame(f, bg=BG)
        bar.pack(fill="x", padx=22, pady=6)
        self.bench_btn = tk.Button(bar, text="▶ Uruchom test sprzętu (~10 s)",
                                   bg=GREEN, fg="#06250F", relief="flat",
                                   padx=18, pady=9, cursor="hand2",
                                   font=("Segoe UI", 12, "bold"),
                                   command=self._run_benchmark_ui)
        self.bench_btn.pack(side="left")
        self.bench_status = tk.Label(bar, text="", bg=BG, fg=MUTED,
                                     font=("Segoe UI", 9))
        self.bench_status.pack(side="left", padx=12)
        tk.Button(bar, text="✔ Zastosuj rekomendacje do FocusIt", bg=ACCENT,
                  fg="#03150A", relief="flat", padx=14, pady=9, cursor="hand2",
                  font=("Segoe UI", 10, "bold"),
                  command=self._apply_recommendations).pack(side="left")

        cards = tk.Frame(f, bg=BG)
        cards.pack(fill="x", padx=22, pady=6)
        self.bench_labels: dict[str, tk.Label] = {}
        for key, title in [("cpu", "Procesor"), ("ram", "Pamięć RAM"),
                           ("disk", "Dysk"), ("gpu", "Karta graficzna"),
                           ("tier", "Klasa sprzętu")]:
            card = tk.Frame(cards, bg=CARD, highlightthickness=1,
                            highlightbackground=BORDER)
            card.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(card, text=title, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(pady=(8, 0))
            lbl = tk.Label(card, text="—", bg=CARD, fg=TEXT,
                           font=("Segoe UI", 11, "bold"), wraplength=170)
            lbl.pack(pady=(0, 9), padx=4)
            self.bench_labels[key] = lbl

        self.bench_text = tk.Text(f, bg=CARD, fg=TEXT, relief="flat",
                                  font=("Segoe UI", 10), wrap="word",
                                  insertbackground=TEXT, height=12)
        self.bench_text.pack(fill="both", expand=True, padx=22, pady=6)
        saved = self.store.settings.get("last_benchmark") or {}
        if saved:
            try:
                self.benchmark_result = BenchmarkResult(**{
                    k: saved[k] for k in BenchmarkResult().__dict__ if k in saved})
                self._show_benchmark()
            except Exception:
                pass

        gfx = tk.LabelFrame(f, text=" Grafika w grach Unreal Engine (np. Fortnite) ",
                            bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"))
        gfx.pack(fill="x", padx=22, pady=8)
        tk.Label(gfx, text="Wskaż plik GameUserSettings.ini gry — FocusIt pokaże "
                           "obecne ustawienia, a po kliknięciu zapisze wersję "
                           "dopasowaną do Twojego sprzętu (z kopią zapasową).",
                 bg=BG, fg=TEXT, font=("Segoe UI", 9), wraplength=820,
                 justify="left").pack(padx=12, pady=(8, 2), anchor="w")
        grow = tk.Frame(gfx, bg=BG)
        grow.pack(padx=12, pady=8, anchor="w")
        tk.Button(grow, text="📂 Wybierz GameUserSettings.ini…", bg=CARD,
                  fg=TEXT, relief="flat", padx=12, pady=5, cursor="hand2",
                  command=self._pick_ue_file).pack(side="left")
        tk.Button(grow, text="🎨 Dopasuj grafikę do sprzętu", bg=CARD, fg=TEXT,
                  relief="flat", padx=12, pady=5, cursor="hand2",
                  command=self._apply_ue).pack(side="left", padx=6)
        tk.Button(grow, text="↩ Przywróć oryginał", bg=CARD, fg=TEXT,
                  relief="flat", padx=12, pady=5, cursor="hand2",
                  command=self._restore_ue).pack(side="left")
        self.ue_path_label = tk.Label(gfx, text="Nie wybrano pliku.",
                                      bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.ue_path_label.pack(padx=12, pady=(0, 8), anchor="w")

    def _bench_progress(self, msg: str) -> None:
        self.root.after(0, lambda: self.bench_status.configure(text=msg))

    def _run_benchmark_ui(self) -> None:
        self.bench_btn.configure(state="disabled")
        self.bench_status.configure(text="Testuję… nie zamykaj programu.")

        def work() -> None:
            try:
                result = run_benchmark(progress=self._bench_progress)
                self.benchmark_result = result
                self.store.settings["last_benchmark"] = result.to_dict()
                self.store.save()
                self.root.after(0, self._show_benchmark)
            except Exception as exc:
                self.root.after(0, lambda exc=exc: self.bench_status.configure(
                    text=f"Test nie powiódł się: {exc}"))
            finally:
                self.root.after(0, lambda: self.bench_btn.configure(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    def _show_benchmark(self) -> None:
        r = self.benchmark_result
        if not r:
            return
        self.bench_labels["cpu"].configure(
            text=f"{r.cpu_mbs:.0f} pkt\n({r.cpu_threads} wątków)")
        self.bench_labels["ram"].configure(
            text=f"{r.ram_total_gb:.0f} GB\n{r.ram_mbs:.0f} MB/s")
        self.bench_labels["disk"].configure(
            text=f"zapis {r.disk_write_mbs:.0f}\nodczyt {r.disk_read_mbs:.0f} MB/s")
        self.bench_labels["gpu"].configure(
            text=f"{r.gpu_vram_gb:.0f} GB VRAM\n{r.gpu_name[:26]}")
        color = GREEN if r.score >= 66 else (GOLD if r.score >= 40 else RED)
        self.bench_labels["tier"].configure(text=f"{r.tier}\n{r.score}/100", fg=color)
        rec = device_recommendations(r)
        lines = [f"Klasa sprzętu: {rec['sprzęt']}", "", "🎨 Zalecana grafika w grach:"]
        lines += [f"• {k}: {v}" for k, v in rec["grafika"].items()]
        lines += ["", "⚙ Rekomendacje dla FocusIt:"]
        lines += [f"• {k}: {v}" for k, v in rec["focusit"].items()]
        if rec["porady"]:
            lines += ["", "💡 Porady:"]
            lines += [f"• {p}" for p in rec["porady"]]
        self.bench_text.delete("1.0", "end")
        self.bench_text.insert("1.0", "\n".join(lines))
        self.bench_status.configure(text="Test zakończony. Wynik zapisany.")
        self.log(f"Test sprzętu: {r.tier} ({r.score}/100), CPU {r.cpu_mbs:.0f}, "
                 f"RAM {r.ram_total_gb:.0f} GB, GPU {r.gpu_vram_gb:.0f} GB.")

    def _apply_recommendations(self) -> None:
        r = self.benchmark_result
        if not r:
            messagebox.showinfo("FocusIt", "Najpierw uruchom test sprzętu.")
            return
        if r.ram_total_gb and r.ram_total_gb < 16:
            self.freeze_var.set(True)
            mode_note = "Włączono ZAMRAŻANIE procesów (bezpieczne przy <16 GB RAM)."
        else:
            mode_note = "Tryb izolacji zostaje głównym trybem sesji (masz zapas RAM)."
        if r.cpu_mbs and r.cpu_mbs < 300:
            self.store.settings["stop_services"] = ["DiagTrack", "SysMain", "BITS"]
            if hasattr(self, "service_vars"):
                for name, var in self.service_vars.items():
                    var.set(name in self.store.settings["stop_services"])
            self.store.save()
        self.log(f"Zastosowano rekomendacje sprzętu ({r.tier}): {mode_note}")
        messagebox.showinfo("FocusIt", f"Zastosowano rekomendacje dla klasy "
                                       f"„{r.tier}”.\n{mode_note}\n"
                                       "Plan zasilania sesji: wysoka wydajność.")

    def _pick_ue_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Wybierz GameUserSettings.ini gry (Unreal Engine)",
            filetypes=[("Ustawienia UE", "GameUserSettings.ini"),
                       ("INI", "*.ini"), ("Wszystkie", "*.*")])
        if path:
            self._ue_path = path
            current = ue_current_settings(Path(path))
            shown = ", ".join(f"{k}={v}" for k, v in list(current.items())[:8])
            self.ue_path_label.configure(
                text=f"{path}\nObecne: {shown or 'brak kluczy sg.*'}")
            self.log(f"Wybrano plik grafiki UE: {path}")

    def _apply_ue(self) -> None:
        path = getattr(self, "_ue_path", "")
        if not path:
            messagebox.showinfo("FocusIt", "Najpierw wybierz plik GameUserSettings.ini.")
            return
        r = self.benchmark_result
        tier = r.tier if r else "Średni"
        vram = r.gpu_vram_gb if r else 0.0
        changes = ue_recommended_changes(tier, vram)
        preview = "\n".join(f"{k} = {v}" for k, v in list(changes.items())[:8])
        if not messagebox.askyesno(
                "FocusIt — dopasowanie grafiki",
                f"Zapiszę ustawienia grafiki dla klasy „{tier}” "
                f"(plik: {Path(path).name}):\n\n{preview}\n…\n\n"
                "Gra musi być WYŁĄCZONA. Oryginał trafi do kopii zapasowej "
                "i przywrócisz go jednym kliknięciem. Kontynuować?"):
            return
        msg = apply_ue_settings(Path(path), changes)
        self.log(msg)
        messagebox.showinfo("FocusIt", msg)

    def _restore_ue(self) -> None:
        path = getattr(self, "_ue_path", "")
        if not path:
            messagebox.showinfo("FocusIt", "Najpierw wybierz plik GameUserSettings.ini.")
            return
        msg = restore_ue_settings(Path(path))
        self.log(msg)
        messagebox.showinfo("FocusIt", msg)

    # --------------------------------------------------------------- HISTORIA
    def _build_history_page(self, f: tk.Frame) -> None:
        self._header(f, "📊 Historia sesji",
                     "Podsumowanie poprzednich sesji FocusIt.")
        cols = ("data", "preset", "cel", "zamkniete", "ram", "czas")
        self.hist_tree = ttk.Treeview(f, columns=cols, show="headings", height=22)
        for col, txt, w in [("data", "Data", 160), ("preset", "Preset", 120),
                            ("cel", "Gra/program", 220),
                            ("zamkniete", "Zamknięte procesy", 140),
                            ("ram", "Szac. zwolniony RAM", 170),
                            ("czas", "Czas sesji", 110)]:
            self.hist_tree.heading(col, text=txt)
            self.hist_tree.column(col, width=w)
        self.hist_tree.pack(fill="both", expand=True, padx=22, pady=8)
        tk.Label(f, text="Zwolniony RAM w ostatnich sesjach (MB):", bg=BG,
                 fg=MUTED, font=("Segoe UI", 9)).pack(padx=22, anchor="w")
        self.hist_chart = tk.Canvas(f, bg=CARD, height=110, highlightthickness=0)
        self.hist_chart.pack(fill="x", padx=22, pady=4)
        self.hist_stats = tk.Label(f, text="", bg=BG, fg=MUTED,
                                   font=("Segoe UI", 10))
        self.hist_stats.pack(padx=22, pady=6, anchor="w")

    # ------------------------------------------------------------- USTAWIENIA
    def _build_settings_page(self, f: tk.Frame) -> None:
        self._header(f, "⚙️ Ustawienia i bezpieczeństwo")
        tk.Label(f, text="Aplikacje, które FocusIt ma ZAWSZE zachowywać "
                         "(po jednej nazwie pliku w wierszu, np. discord.exe):",
                 bg=BG, fg=TEXT, font=("Segoe UI", 10)).pack(padx=22, anchor="w")
        self.keep_text = tk.Text(f, bg=CARD, fg=TEXT, height=7, relief="flat",
                                 font=("Consolas", 10), insertbackground=TEXT)
        self.keep_text.pack(fill="x", padx=22, pady=6)

        self.set_sim = tk.BooleanVar()
        self.set_restore_apps = tk.BooleanVar()
        self.set_restore_power = tk.BooleanVar()
        self.set_confirm = tk.BooleanVar()
        self.set_auto = tk.BooleanVar()
        self.set_auto_stop = tk.BooleanVar()
        self.set_widget = tk.BooleanVar()
        self.set_hotkey = tk.BooleanVar()
        self.set_updates = tk.BooleanVar()
        self.set_ov_enabled = tk.BooleanVar()
        self.set_ov_click = tk.BooleanVar()
        for var, txt in [
            (self.set_sim, "Domyślnie włączaj SYMULACJĘ przy starcie programu"),
            (self.set_restore_apps, "Po sesji ponownie uruchamiaj zamknięte aplikacje"),
            (self.set_restore_power, "Po sesji przywracaj poprzedni plan zasilania"),
            (self.set_confirm, "Wymagaj potwierdzenia przed trybem IZOLACJI na żywo"),
            (self.set_auto, "AUTO-SESJA: sam startuj sesję, gdy wykryjesz grę z Biblioteki"),
            (self.set_auto_stop, "AUTO-STOP: kończ auto-sesję po zamknięciu gry"),
            (self.set_widget, "Pokazuj mini-widget podczas sesji"),
            (self.set_hotkey, "Skrót globalny Ctrl+Alt+F (start/stop sesji)"),
            (self.set_updates, "Sprawdzaj nowe wersje programu przy starcie"),
            (self.set_ov_enabled, "Nakładka z widżetami podczas sesji (Panel gry)"),
            (self.set_ov_click, "Nakładka przepuszcza kliknięcia (Windows, poza trybem edycji)"),
        ]:
            tk.Checkbutton(f, text=txt, variable=var, bg=BG, fg=TEXT,
                           activebackground=BG, activeforeground=TEXT,
                           selectcolor=CARD, font=("Segoe UI", 10)).pack(
                               padx=22, anchor="w", pady=2)

        theme_box = tk.LabelFrame(f, text=" Motyw interfejsu ", bg=BG,
                                  fg=ACCENT, font=("Segoe UI", 10, "bold"))
        theme_box.pack(fill="x", padx=22, pady=10)
        self.set_theme = tk.StringVar(value=self.store.settings.get("theme", "neon"))
        tk.Radiobutton(theme_box, text="⬢ Neon Honeycomb — matowa czerń i zielone neony",
                       value="neon", variable=self.set_theme, bg=BG, fg=TEXT,
                       activebackground=BG, activeforeground=TEXT,
                       selectcolor=CARD, font=("Segoe UI", 10, "bold")).pack(
                           padx=14, pady=(8, 2), anchor="w")
        tk.Radiobutton(theme_box, text="Klasyczny — grafit i fiolet",
                       value="classic", variable=self.set_theme, bg=BG, fg=TEXT,
                       activebackground=BG, activeforeground=TEXT,
                       selectcolor=CARD, font=("Segoe UI", 10)).pack(
                           padx=14, anchor="w")
        tk.Label(theme_box, text="Zmiana motywu wymaga ponownego uruchomienia programu.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(
                     padx=14, pady=(2, 8), anchor="w")

        tk.Button(f, text="💾 Zapisz ustawienia", bg=ACCENT, fg="#03150A",
                  font=("Segoe UI", 11, "bold"), relief="flat", padx=18, pady=7,
                  cursor="hand2", command=self._save_settings).pack(
                      padx=22, pady=12, anchor="w")

        info = (
            "🔒 ZASADY BEZPIECZEŃSTWA FocusIt — program NIGDY nie zamknie:\n"
            "• procesów jądra i usług Windows (svchost, csrss, lsass, winlogon…),\n"
            "• niczego z katalogu C:\\Windows ani procesów kont systemowych,\n"
            "• pulpitu i obsługi klawiatury (explorer, dwm, ctfmon…),\n"
            "• sterowników grafiki i dźwięku (NVIDIA / AMD / Intel / Realtek),\n"
            "• antywirusa Windows Defender,\n"
            "• wybranej gry, jej launchera, procesów potomnych (np. anti-cheatu)\n"
            "  i programów z tego samego folderu co gra,\n"
            "• procesów, do których nie ma dostępu (brak ścieżki = pomijamy),\n"
            "• aplikacji z Twojej listy „Zachowaj” powyżej.\n"
            "Każdy proces jest dodatkowo sprawdzany tuż przed zamknięciem, "
            "a najpierw wysyłana jest grzeczna prośba o zamknięcie (jak kliknięcie ✕)."
        )
        tk.Label(f, text=info, bg=CARD, fg=TEXT, justify="left",
                 font=("Segoe UI", 9), padx=14, pady=10,
                 wraplength=900).pack(fill="x", padx=22, pady=8)

    # ----------------------------------------------------------------- pomoc
    def log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")

    def _draw_sidebar(self) -> None:
        c = self.side_canvas
        w = max(c.winfo_width(), 225)
        draw_honeycomb(c, w, 104, r=15)
        c.create_text(19, 37, anchor="w", text="⚡ FocusIt", fill="#0B2E12",
                      font=("Segoe UI", 22, "bold"))
        c.create_text(18, 36, anchor="w", text="⚡ FocusIt", fill="white",
                      font=("Segoe UI", 22, "bold"))
        c.create_text(18, 66, anchor="w", text="⬡ 100% mocy dla Twojej gry",
                      fill=NEON, font=("Segoe UI", 9, "bold"))
        c.create_text(18, 86, anchor="w", text="NEON HONEYCOMB // GAME BAR",
                      fill=MUTED, font=("Consolas", 7))

    def _draw_banner(self) -> None:
        c = self.banner
        w = max(c.winfo_width(), 600)
        h = 86
        draw_honeycomb(c, w, h, r=25)
        # matowa "karta" pod tekstem, żeby był czytelny na wzorze
        c.create_rectangle(10, 10, 560, h - 10, fill="#070806", outline=BORDER)
        c.create_text(25, 34, anchor="w", text="Gotowy do gry?", fill="#0B2E12",
                      font=("Segoe UI", 20, "bold"))
        c.create_text(24, 33, anchor="w", text="Gotowy do gry?", fill="white",
                      font=("Segoe UI", 20, "bold"))
        c.create_text(24, 60, anchor="w",
                      text="⬡ Jeden klik i komputer pracuje tylko dla Twojej gry.",
                      fill=NEON, font=("Segoe UI", 10, "bold"))
        active = bool(self.session and self.session.active)
        pill = NEON if active else ACCENT
        label = "SESJA AKTYWNA" if active else "SYSTEM GOTOWY"
        x0 = w - 208
        c.create_rectangle(x0 - 8, 24, w - 14, 48, fill="#070806", outline=pill)
        c.create_oval(x0, 30, x0 + 11, 41, fill=pill, outline="")
        c.create_text(x0 + 18, 36, anchor="w", text=label, fill="white",
                      font=("Segoe UI", 9, "bold"))

    def _draw_chart(self) -> None:
        c = self.chart
        w = max(c.winfo_width(), 300)
        h = 86
        c.delete("all")
        for frac in (0.25, 0.5, 0.75):
            y = h * frac
            c.create_line(0, y, w, y, fill=BORDER)
        for hist, color in ((self.cpu_hist, NEON), (self.ram_hist, CYAN)):
            if len(hist) < 2:
                continue
            step = w / (len(hist) - 1)
            points = []
            for i, v in enumerate(hist):
                points += [i * step, h - 4 - (min(v, 100) / 100) * (h - 10)]
            c.create_line(*points, fill=color, width=2, smooth=True)

    def _auto_check(self) -> None:
        """Auto-sesja: wykryj start gry z biblioteki / koniec gry."""
        s = self.store.settings
        active = bool(self.session and self.session.active)
        if active and self.auto_started and s.get("auto_stop", True):
            _, exe, name = self._resolve_target()
            if not find_target_pid(exe, name):
                self.log("Gra została zamknięta — kończę auto-sesję i przywracam ustawienia.")
                self.stop_session(silent=True)
                messagebox.showinfo("FocusIt", "Gra zamknięta. Sesja zakończona, "
                                               "ustawienia przywrócone.")
            return
        if active or not s.get("auto_session", False) or not self.games:
            return
        running = {p.stem for p in list_processes() if p.exe}
        for game in self.games:
            if game.exe and game.stem in running:
                self.log(f"Wykryto uruchomioną grę z biblioteki: {game.name} "
                         "— startuję sesję automatycznie.")
                self._select_game(game)
                self.start_session(from_auto=True)
                return

    def _tick_stats(self) -> None:
        self._tick_count += 1
        try:
            s = get_system_stats()
            self.stat_labels["cpu"].configure(text=f"{s['cpu_percent']:.0f}%")
            self.stat_labels["ram"].configure(
                text=f"{s['ram_used_gb']:.1f} / {s['ram_total_gb']:.1f} GB")
            self.stat_labels["free"].configure(text=f"{s['ram_available_mb']} MB")
            self.stat_labels["procs"].configure(text=str(s["process_count"]))
            self.cpu_hist.append(s["cpu_percent"])
            self.ram_hist.append(s["ram_percent"])
            self._draw_chart()
            self._stat_pct.update({
                "cpu": s["cpu_percent"], "ram": s["ram_percent"],
                "free": (s["ram_available_mb"] /
                         max(s["ram_total_gb"] * 1024, 1) * 100),
                "procs": min(s["process_count"] / 2, 100)})
            for key, pct in self._stat_pct.items():
                bar = self.stat_bars[key]
                bw = max(bar.winfo_width(), 60)
                bar.delete("all")
                bar.create_rectangle(0, 0, bw, 5, fill=BORDER, outline="")
                color = GREEN if pct < 60 else (GOLD if pct < 85 else RED)
                if key == "free":
                    color = GREEN if pct > 25 else RED
                bar.create_rectangle(0, 0, bw * min(pct, 100) / 100, 5,
                                     fill=color, outline="")
            if self._tick_count % 5 == 1:
                self._gpu_cache = get_gpu_stats()
            g = self._gpu_cache
            self.stat_labels["gpu"].configure(
                text=(f"{g['percent']:.0f}% / {g['temp_c']:.0f}°C" if g
                      else "— (tylko NVIDIA)"))
            if g:
                self._stat_pct["gpu"] = g["percent"]
            if self._tick_count % 10 == 1:
                procs = [p for p in list_processes() if p.exe]
                top = procs[:5]
                self.top_label.configure(text="Najcięższe procesy:\n" + "\n".join(
                    f"• {p.name} — {p.memory_mb:.0f} MB" for p in top))
                heavy = {"chrome.exe", "firefox.exe", "msedge.exe", "spotify.exe",
                         "steamwebhelper.exe", "discord.exe", "teams.exe",
                         "onedrive.exe", "skype.exe"}
                keep = {k.lower() for k in
                        self.store.settings.get("keep_always", [])}
                tips = [f"{p.name} ({p.memory_mb:.0f} MB)" for p in procs
                        if p.name.lower() in heavy and p.memory_mb > 250
                        and p.name.lower() not in keep][:3]
                self.sug_label.configure(
                    text=("💡 Sugestia: przed grą warto zamknąć: "
                          + ", ".join(tips)) if tips else "")
            if self._tick_count % 3 == 0:
                self._auto_check()
            if self._overlays:
                self._update_overlay_texts()
        except Exception:
            pass
        if self.session and self.session.active:
            elapsed = int(time.time() - self.session_started)
            extra = ""
            if self.pomodoro_left > 0:
                self.pomodoro_left -= 1
                phase = "SKUPienie" if self.pomodoro_phase == "focus" else "PRZERWA"
                extra = f" | 🍅 {phase}: {self.pomodoro_left // 60:02d}:{self.pomodoro_left % 60:02d}"
                if self.pomodoro_left == 0:
                    self.root.bell()
                    preset_min = int(self.session.preset.get("pomodoro_minutes") or 0)
                    if self.pomodoro_phase == "focus" and preset_min:
                        self.pomodoro_phase, self.pomodoro_left = "break", 5 * 60
                        self.log("🍅 Koniec bloku nauki — 5 minut przerwy!")
                    elif preset_min:
                        self.pomodoro_phase = "focus"
                        self.pomodoro_left = preset_min * 60
                        self.log("🍅 Przerwa skończona — wracamy do nauki!")
            txt = (f"⏱ Sesja: {elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:"
                   f"{elapsed % 60:02d}{extra}")
            self.session_label.configure(text=txt)
            if self._widget is not None and hasattr(self, "_widget_label"):
                try:
                    self._widget_label.configure(text=txt)
                except tk.TclError:
                    self._widget = None
        self.root.after(1000, self._tick_stats)

    # ------------------------------------------------------------------- cel
    def refresh_targets(self) -> None:
        procs = [p for p in list_processes() if p.exe]
        self._target_procs: list[ProcessInfo] = procs[:90]
        values = [f"{p.name}  (PID {p.pid}, {p.memory_mb:.0f} MB)" for p in self._target_procs]
        self.target_combo["values"] = values
        if values:
            self.target_combo.current(0)

    def _browse_exe(self) -> None:
        path = filedialog.askopenfilename(
            title="Wybierz plik gry/programu",
            filetypes=[("Programy", "*.exe"), ("Wszystkie pliki", "*.*")])
        if path:
            self.target_info.configure(text=path)
            self._custom_exe = path
            self.target_combo.set(Path(path).name)

    def _resolve_target(self) -> tuple[int | None, str, str]:
        """Zwraca (pid, exe, nazwa) wybranego celu."""
        custom = getattr(self, "_custom_exe", "")
        idx = self.target_combo.current()
        if custom and self.target_combo.get() == Path(custom).name:
            pid = find_target_pid(custom)
            return pid, custom, Path(custom).name
        if 0 <= idx < len(getattr(self, "_target_procs", [])):
            p = self._target_procs[idx]
            return p.pid, p.exe, p.name
        text = self.target_combo.get().strip()
        if text:
            return find_target_pid(name=text), "", text
        return None, "", ""

    # ---------------------------------------------------------------- presety
    def refresh_preset_lists(self) -> None:
        for w in self.preset_radios.winfo_children():
            w.destroy()
        self._preset_cards: dict[str, list] = {}
        for p in self.store.presets:
            selected = (p["name"] == self.preset_var.get())
            card = tk.Frame(self.preset_radios,
                            bg=ACCENT if selected else CARD,
                            highlightthickness=2,
                            highlightbackground=ACCENT if selected else BORDER)
            card.pack(side="left", padx=4, pady=2)
            widgets = [card]
            for text, size, bold, color in [
                    (p.get("icon", "🎯"), 17, False, TEXT),
                    (p["name"], 10, True, TEXT),
                    ("IZOLACJA" if p.get("mode") == "isolation" else "ŁAGODNY",
                     7, True, GOLD if p.get("mode") == "isolation" else MUTED)]:
                lbl = tk.Label(card, text=text, bg=ACCENT if selected else CARD,
                               fg=color, font=("Segoe UI", size,
                                               "bold" if bold else "normal"))
                lbl.pack(padx=16, pady=(1, 0))
                widgets.append(lbl)

            def pick(_e=None, name=p["name"]):
                self.preset_var.set(name)
                self.refresh_preset_lists()

            def hover(_e, c=card, w=widgets, name=p["name"]):
                if self.preset_var.get() != name:
                    for x in w:
                        x.configure(bg=CARD_HOVER)

            def unhover(_e, w=widgets, name=p["name"]):
                if self.preset_var.get() != name:
                    for x in w:
                        x.configure(bg=CARD)

            for x in widgets:
                x.bind("<Button-1>", pick)
                x.bind("<Enter>", hover)
                x.bind("<Leave>", unhover)
            self._preset_cards[p["name"]] = widgets
        self.preset_list.delete(0, "end")
        for p in self.store.presets:
            self.preset_list.insert("end", f"{p.get('icon', '🎯')} {p['name']}")
        self._preset_changed()

    def _preset_changed(self) -> None:
        p = self.store.get_preset(self.preset_var.get())
        if p:
            mode = "izolacja" if p.get("mode") == "isolation" else "łagodny"
            self.preset_desc.configure(
                text=f"{p.get('description', '')} (tryb: {mode})")

    def _listbox_preset(self) -> dict | None:
        sel = self.preset_list.curselection()
        if not sel:
            return self.store.presets[0] if self.store.presets else None
        text = self.preset_list.get(sel[0])
        name = text.split(" ", 1)[1] if " " in text else text
        return self.store.get_preset(name)

    def _preset_selected(self, _event=None) -> None:
        p = self._listbox_preset()
        if not p:
            return
        for key in ("name", "icon", "description"):
            self.p_fields[key].set(p.get(key, ""))
        for key in ("close_apps", "launch_apps", "keep_apps"):
            self.p_fields[key].set(", ".join(p.get(key, [])))
        self.p_mode.set(p.get("mode", "gentle"))
        self.p_power.set(bool(p.get("power_high_performance")))
        self.p_priority.set(bool(p.get("raise_priority")))
        self.p_pomodoro.set(str(p.get("pomodoro_minutes", 0)))

    @staticmethod
    def _split(text: str) -> list[str]:
        return [x.strip() for x in text.replace(";", ",").split(",") if x.strip()]

    def _save_preset(self) -> None:
        name = self.p_fields["name"].get().strip()
        if not name:
            messagebox.showwarning("FocusIt", "Podaj nazwę presetu.")
            return
        try:
            pomodoro = int(self.p_pomodoro.get() or 0)
        except ValueError:
            pomodoro = 0
        preset = {
            "name": name,
            "icon": self.p_fields["icon"].get().strip() or "🎯",
            "description": self.p_fields["description"].get().strip(),
            "mode": self.p_mode.get(),
            "close_apps": self._split(self.p_fields["close_apps"].get()),
            "launch_apps": self._split(self.p_fields["launch_apps"].get()),
            "keep_apps": self._split(self.p_fields["keep_apps"].get()),
            "power_high_performance": self.p_power.get(),
            "raise_priority": self.p_priority.get(),
            "pomodoro_minutes": pomodoro,
            "built_in": False,
        }
        old = self.store.get_preset(name)
        if old and old.get("built_in"):
            messagebox.showinfo("FocusIt", "To preset wbudowany — zapiszę go jako "
                                           "nową kopię. Zmień nazwę, aby nie nadpisać oryginału.")
            return
        self.store.upsert_preset(preset)
        self.preset_var.set(name)
        self.refresh_preset_lists()
        self.log(f"Zapisano preset „{name}”.")

    def _new_preset(self) -> None:
        for var in self.p_fields.values():
            var.set("")
        self.p_fields["icon"].set("🎯")
        self.p_mode.set("gentle")

    def _copy_preset(self) -> None:
        p = self._listbox_preset()
        if p:
            self._preset_selected()
            self.p_fields["name"].set(p["name"] + " — kopia")

    def _delete_preset(self) -> None:
        p = self._listbox_preset()
        if p and self.store.delete_preset(p["name"]):
            self.refresh_preset_lists()
            self.log(f"Usunięto preset „{p['name']}”.")
        elif p:
            messagebox.showinfo("FocusIt", "Presetów wbudowanych nie można usunąć.")

    # ----------------------------------------------------------------- plan
    def _current_preset_with_mode(self) -> dict:
        preset = copy.deepcopy(self.store.get_preset(self.preset_var.get())
                        or self.store.presets[0])
        if self.mode_var.get() in ("gentle", "isolation"):
            preset["mode"] = self.mode_var.get()
        # profil konkretnej gry (z Biblioteki) ma pierwszeństwo
        _, exe, _ = self._resolve_target()
        prof = self.store.game_profile(exe)
        if prof:
            if prof.get("mode"):
                preset["mode"] = prof["mode"]
            preset["keep_apps"] = list(set(preset.get("keep_apps", []))
                                       | set(prof.get("keep_apps", [])))
            preset["close_apps"] = list(set(preset.get("close_apps", []))
                                        | set(prof.get("close_apps", [])))
            affinity = parse_affinity(prof.get("affinity", ""))
            if affinity:
                preset["cpu_affinity"] = affinity
        preset["freeze_processes"] = bool(
            getattr(self, "freeze_var", tk.BooleanVar(value=False)).get())
        return preset

    def _make_session(self) -> FocusSession:
        pid, exe, name = self._resolve_target()
        return FocusSession(self._current_preset_with_mode(),
                            self.store.settings, target_pid=pid,
                            target_exe=exe, target_name=name, log=self.log)

    def preview_plan(self) -> None:
        session = self._make_session()
        plan = session.build_plan()
        self.plan_summary.configure(text=plan.summary())
        self._tree_rows = []
        for d in plan.decisions:
            self._tree_rows.append((
                "☠ ZAMKNIJ" if d.kill else "✓ zachowaj", str(d.proc.pid),
                d.proc.name, f"{d.proc.memory_mb:.0f}",
                f"[{d.category}] {d.reason}", d.proc.exe))
        self._filter_tree()
        self._show_page("procesy")
        self.log(f"Podgląd planu: {plan.summary()}")

    def _filter_tree(self) -> None:
        q = self.search_var.get().lower() if hasattr(self, "search_var") else ""
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self._tree_rows:
            if q and q not in " ".join(row).lower():
                continue
            tag = "kill" if row[0].startswith("☠") else "keep"
            self.tree.insert("", "end", values=row, tags=(tag,))

    def _tree_double_click(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        name = self.tree.item(sel[0])["values"][2]
        keep = self.store.settings.setdefault("keep_always", [])
        if name not in keep:
            keep.append(name)
            self.store.save()
            self._load_settings_to_ui()
            self.log(f"Dodano {name} do listy „Zachowaj” — odśwież podgląd planu.")
            messagebox.showinfo("FocusIt", f"{name} będzie od teraz zawsze zachowywany.")

    # --------------------------------------------------------------- nakładki
    def _save_overlay_choices(self) -> None:
        s = self.store.settings
        s["overlay_widgets"] = [k for k, v in self.ov_vars.items() if v.get()]
        s["overlay_opacity"] = int(self.ov_opacity.get())
        self.store.save()
        if self._overlays:   # odśwież na żywo
            for_session = self._overlays_for_session
            self._hide_overlays()
            self._show_overlays(for_session=for_session)

    def _overlay_edit_toggled(self) -> None:
        if self._overlays:
            for_session = self._overlays_for_session
            self._hide_overlays()
            self._show_overlays(for_session=for_session)

    def _toggle_overlays_preview(self) -> None:
        if self._overlays and not self._overlays_for_session:
            self._hide_overlays()
        else:
            self._show_overlays(for_session=False)

    def _show_overlays(self, for_session: bool) -> None:
        self._hide_overlays()
        self._overlays_for_session = for_session
        widgets = self.store.settings.get("overlay_widgets",
                                          ["czas", "statystyki", "przyciski"])
        opacity = int(self.store.settings.get("overlay_opacity", 85)) / 100
        positions = self.store.settings.get("overlay_positions", {})
        try:
            screen_w = self.root.winfo_screenwidth()
        except Exception:
            screen_w = 1280
        for idx, kind in enumerate(widgets):
            win = tk.Toplevel(self.root)
            win.title(f"FocusIt nakładka: {kind}")
            win.configure(bg="#050705")
            win.configure(highlightthickness=1, highlightbackground=NEON)
            try:
                win.overrideredirect(True)      # bez ramki okna
                win.attributes("-topmost", True)
                win.attributes("-alpha", opacity)
            except tk.TclError:
                pass
            saved = positions.get(kind)
            if saved:
                x, y = int(saved[0]), int(saved[1])
            else:
                x, y = max(screen_w - 265, 0), 18 + idx * 96
            try:
                win.geometry(f"245x84+{x}+{y}")
            except tk.TclError:
                pass
            head = tk.Label(win, text="⬡ FocusIt", bg="#050705", fg=NEON,
                            font=("Segoe UI", 8, "bold"))
            head.pack(anchor="w", padx=10, pady=(6, 0))
            lbl = tk.Label(win, text="…", bg="#050705", fg=TEXT,
                           font=("Segoe UI", 11, "bold"), justify="left")
            lbl.pack(anchor="w", padx=10)
            self._overlay_labels[kind] = lbl
            if kind == "przyciski":
                brow = tk.Frame(win, bg="#050705")
                brow.pack(anchor="w", padx=8, pady=3)
                tk.Button(brow, text="■ Koniec sesji", bg=RED, fg="white",
                          relief="flat", padx=8, pady=2, cursor="hand2",
                          font=("Segoe UI", 8, "bold"),
                          command=lambda: self.stop_session()).pack(side="left")
                tk.Button(brow, text="🌐 DNS", bg=CARD, fg=TEXT, relief="flat",
                          padx=8, pady=2, cursor="hand2", font=("Segoe UI", 8),
                          command=lambda: flush_dns(self.log)).pack(
                              side="left", padx=4)
                tk.Button(brow, text="✕ Ukryj", bg=CARD, fg=TEXT, relief="flat",
                          padx=8, pady=2, cursor="hand2", font=("Segoe UI", 8),
                          command=self._hide_overlays).pack(side="left")
            for widget in (win, head, lbl):
                self._bind_drag(widget, win, kind)
            self._overlays[kind] = win
            self._apply_clickthrough(win)
        self._update_overlay_texts()

    def _bind_drag(self, widget, win: tk.Toplevel, kind: str) -> None:
        def start(event):
            win._drag_x, win._drag_y = event.x, event.y  # type: ignore[attr-defined]

        def move(event):
            if not self.ov_edit.get():
                return
            x = win.winfo_x() + event.x - getattr(win, "_drag_x", 0)
            y = win.winfo_y() + event.y - getattr(win, "_drag_y", 0)
            try:
                win.geometry(f"+{x}+{y}")
            except tk.TclError:
                pass

        def end(_event):
            if self.ov_edit.get():
                pos = self.store.settings.setdefault("overlay_positions", {})
                pos[kind] = [win.winfo_x(), win.winfo_y()]
                self.store.save()

        widget.bind("<Button-1>", start)
        widget.bind("<B1-Motion>", move)
        widget.bind("<ButtonRelease-1>", end)

    def _apply_clickthrough(self, win: tk.Toplevel) -> None:
        """Windows: klikanie przechodzi przez nakładkę (poza trybem edycji)."""
        if self.ov_edit.get() or not self.store.settings.get(
                "overlay_clickthrough", False):
            return
        try:
            import ctypes
            hwnd = win.winfo_id()
            GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        except Exception:
            pass

    def _update_overlay_texts(self) -> None:
        for kind, lbl in self._overlay_labels.items():
            try:
                if kind == "czas":
                    if self.session and self.session.active:
                        e = int(time.time() - self.session_started)
                        lbl.configure(text=f"⏱ {e // 3600:02d}:"
                                           f"{(e % 3600) // 60:02d}:{e % 60:02d}")
                    else:
                        lbl.configure(text="⏱ brak sesji")
                elif kind == "statystyki":
                    cpu = self.cpu_hist[-1] if self.cpu_hist else 0
                    ram = self.ram_hist[-1] if self.ram_hist else 0
                    g = self._gpu_cache
                    gpu = f"{g['percent']:.0f}%" if g else "—"
                    lbl.configure(text=f"CPU {cpu:.0f}%  RAM {ram:.0f}%  GPU {gpu}")
            except tk.TclError:
                pass

    def _hide_overlays(self) -> None:
        for win in self._overlays.values():
            try:
                win.destroy()
            except tk.TclError:
                pass
        self._overlays = {}
        self._overlay_labels = {}
        self._overlays_for_session = False

    # ------------------------------------------------------------- mini-widget
    def _show_widget(self) -> None:
        if self._widget is not None:
            return
        win = tk.Toplevel(self.root)
        win.title("FocusIt — sesja")
        win.configure(bg=PANEL)
        win.attributes("-topmost", True)
        try:
            win.geometry("270x110+40+40")
        except tk.TclError:
            pass
        win.protocol("WM_DELETE_WINDOW", self._hide_widget)
        self._widget_label = tk.Label(win, text="⏱ Sesja: 00:00:00", bg=PANEL,
                                      fg=GOLD, font=("Segoe UI", 12, "bold"))
        self._widget_label.pack(pady=(14, 4))
        tk.Label(win, text="FocusIt dba o wydajność 🎮", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack()
        tk.Button(win, text="■ Zakończ i przywróć", bg=RED, fg="white",
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  font=("Segoe UI", 9, "bold"),
                  command=lambda: self.stop_session()).pack(pady=8)
        self._widget = win

    def _hide_widget(self) -> None:
        if self._widget is not None:
            try:
                self._widget.destroy()
            except tk.TclError:
                pass
            self._widget = None

    # ----------------------------------------------------------------- sesja
    def start_session(self, from_auto: bool = False) -> None:
        if self.session and self.session.active:
            return
        self.auto_started = from_auto
        preset = self._current_preset_with_mode()
        pid, exe, name = self._resolve_target()
        simulate = self.sim_var.get()

        if preset["mode"] == "isolation" and not name:
            messagebox.showwarning(
                "FocusIt", "Tryb IZOLACJI wymaga wybrania gry/programu — "
                            "to wokół niego program sprząta system.")
            return

        # opcjonalne uruchomienie gry przed sprzątaniem (łatwiej wykryć jej procesy)
        if self.launch_target_var.get() and exe and pid is None:
            self.log(launch_app(exe))
            for _ in range(16):
                self.root.update()
                time.sleep(0.5)
                pid = find_target_pid(exe, name)
                if pid:
                    break
            self.log(f"Wykryto proces gry: PID {pid}" if pid
                     else "Nie wykryto jeszcze procesu gry — kontynuuję bez niego.")

        self.session = FocusSession(preset, self.store.settings,
                                    target_pid=pid, target_exe=exe,
                                    target_name=name, log=self.log)
        plan = self.session.build_plan()

        if preset["mode"] == "isolation" and not simulate and not from_auto and \
                self.store.settings.get("confirm_aggressive_mode", True):
            top = "\n".join(f"• {d.proc.name} ({d.proc.memory_mb:.0f} MB)"
                            for d in plan.kill_list[:15])
            more = f"\n… i {len(plan.kill_list) - 15} kolejnych" if len(plan.kill_list) > 15 else ""
            ok = messagebox.askyesno(
                "Potwierdź tryb IZOLACJI",
                f"FocusIt zamknie {len(plan.kill_list)} procesów "
                f"(~{plan.estimated_freed_mb:.0f} MB RAM):\n\n{top}{more}\n\n"
                "Procesy systemowe Windows NIE zostaną ruszone.\n"
                "Zamknięte aplikacje mogą zostać ponownie otwarte po sesji.\n\n"
                "Na pewno kontynuować?")
            if not ok:
                self.log("Anulowano start sesji.")
                self.session = None
                return

        self.session.start(simulate=simulate)
        self.session_started = time.time()
        pom = int(preset.get("pomodoro_minutes") or 0)
        self.pomodoro_phase = "focus"
        self.pomodoro_left = pom * 60 if pom else 0
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        mode_txt = "SYMULACJA" if simulate else "NA ŻYWO"
        self.side_status.configure(
            text=f"● Sesja aktywna: {preset['name']} ({mode_txt})", fg=GREEN)
        self._draw_banner()
        self.session_label.configure(text="⏱ Sesja: 00:00:00")
        self.log(f"=== Sesja „{preset['name']}” rozpoczęta ({mode_txt}) ===")
        if not simulate:
            # zapis stanu: gdyby FocusIt padł, następny start wszystko przywróci
            self.store.save_session_state(self.session.state_dict())
        if self.store.settings.get("show_session_widget", True):
            self._show_widget()
        if self.store.settings.get("overlay_enabled", True):
            self._show_overlays(for_session=True)
        self.refresh_targets()

    def stop_session(self, silent: bool = False) -> None:
        if not self.session:
            return
        summary = self.session.stop()
        self.store.add_history(summary)
        self.store.clear_session_state()
        self.session = None
        self.auto_started = False
        self._hide_widget()
        if self._overlays_for_session:
            self._hide_overlays()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.side_status.configure(text="● Brak aktywnej sesji", fg=MUTED)
        self._draw_banner()
        self.session_label.configure(text="")
        self.refresh_history()
        self.refresh_targets()
        self.log(f"=== Sesja zakończona. Zamknięte: {summary['killed_count']}, "
                 f"zamrożone: {summary.get('suspended_count', 0)}, "
                 f"szac. zwolniono: {summary['estimated_freed_mb']:.0f} MB, "
                 f"czas: {summary['duration_sec'] // 60} min ===")
        if not silent:
            messagebox.showinfo(
                "FocusIt — podsumowanie sesji",
                f"Preset: {summary['preset']}\nCel: {summary['target']}\n"
                f"Czas sesji: {summary['duration_sec'] // 60} min "
                f"{summary['duration_sec'] % 60} s\n"
                f"Zamknięte procesy: {summary['killed_count']} "
                f"(liczba procesów: {summary.get('processes_before', '?')} → "
                f"{summary.get('processes_after', '?')})\n"
                f"Obciążenie procesów w tle: "
                f"{summary.get('bg_load_before', 0):.1f}% → "
                f"{summary.get('bg_load_after', 0):.1f}% CPU\n"
                f"Zamrożone procesy: {summary.get('suspended_count', 0)}\n"
                f"Szacunkowo zwolniony RAM: {summary['estimated_freed_mb']:.0f} MB\n"
                f"Wolny RAM po sesji: {summary.get('ram_available_after_mb', 0)} MB\n"
                f"Przywrócone aplikacje: {len(summary['restored_apps'])}")

    # -------------------------------------------------------------- historia
    def refresh_history(self) -> None:
        for item in self.hist_tree.get_children():
            self.hist_tree.delete(item)
        history = self.store.load_history()
        total_killed = total_ram = total_sec = 0
        for h in history:
            total_killed += h.get("killed_count", 0)
            total_ram += h.get("estimated_freed_mb", 0)
            total_sec += h.get("duration_sec", 0)
            dur = h.get("duration_sec", 0)
            self.hist_tree.insert("", "end", values=(
                h.get("date", ""), h.get("preset", ""), h.get("target", ""),
                h.get("killed_count", 0), f"{h.get('estimated_freed_mb', 0):.0f} MB",
                f"{dur // 60}:{dur % 60:02d}"))
        self.hist_stats.configure(
            text=f"Razem: {len(history)} sesji • zamknięte procesy: {total_killed} • "
                 f"szac. zwolniony RAM: {total_ram:.0f} MB • "
                 f"łączny czas sesji: {total_sec // 3600} h {(total_sec % 3600) // 60} min")
        # wykres słupkowy: ostatnie 15 sesji
        c = self.hist_chart
        c.delete("all")
        recent = list(reversed(history[:15]))
        if recent:
            w = max(c.winfo_width(), 400)
            maxv = max((h.get("estimated_freed_mb", 0) for h in recent), default=1) or 1
            step = w / len(recent)
            for i, h in enumerate(recent):
                v = h.get("estimated_freed_mb", 0)
                bh = 12 + (v / maxv) * 78
                x0 = i * step + 6
                c.create_rectangle(x0, 100 - bh, x0 + step - 12, 100,
                                   fill=ACCENT, outline="")
                c.create_text(x0 + (step - 12) / 2, 106, anchor="n",
                              text=f"{v:.0f}", fill=MUTED, font=("Segoe UI", 7))

    # ------------------------------------------------------------- ustawienia
    def _load_settings_to_ui(self) -> None:
        s = self.store.settings
        self.keep_text.delete("1.0", "end")
        self.keep_text.insert("1.0", "\n".join(s.get("keep_always", [])))
        self.set_sim.set(s.get("simulation_by_default", True))
        self.set_restore_apps.set(s.get("restore_apps_after_session", True))
        self.set_restore_power.set(s.get("restore_power_plan", True))
        self.set_confirm.set(s.get("confirm_aggressive_mode", True))
        self.set_auto.set(s.get("auto_session", False))
        self.set_auto_stop.set(s.get("auto_stop", True))
        self.set_widget.set(s.get("show_session_widget", True))
        self.set_hotkey.set(s.get("hotkey_enabled", True))
        self.set_updates.set(s.get("check_updates", True))
        self.set_ov_enabled.set(s.get("overlay_enabled", True))
        self.set_ov_click.set(s.get("overlay_clickthrough", False))
        if hasattr(self, "set_theme"):
            self.set_theme.set(s.get("theme", "neon"))

    def _save_settings(self) -> None:
        s = self.store.settings
        s["keep_always"] = [x.strip() for x in
                            self.keep_text.get("1.0", "end").splitlines() if x.strip()]
        s["simulation_by_default"] = self.set_sim.get()
        s["restore_apps_after_session"] = self.set_restore_apps.get()
        s["restore_power_plan"] = self.set_restore_power.get()
        s["confirm_aggressive_mode"] = self.set_confirm.get()
        s["auto_session"] = self.set_auto.get()
        s["auto_stop"] = self.set_auto_stop.get()
        s["show_session_widget"] = self.set_widget.get()
        s["hotkey_enabled"] = self.set_hotkey.get()
        s["check_updates"] = self.set_updates.get()
        s["overlay_enabled"] = self.set_ov_enabled.get()
        s["overlay_clickthrough"] = self.set_ov_click.get()
        old_theme = s.get("theme", "neon")
        if hasattr(self, "set_theme"):
            s["theme"] = self.set_theme.get()
        self.store.save()
        if hasattr(self, "set_theme") and s.get("theme") != old_theme:
            messagebox.showinfo("FocusIt", "Motyw zapisany. Uruchom program "
                                           "ponownie, aby zobaczyć nowy wygląd.")
        self.sim_var.set(s["simulation_by_default"])
        self.log("Zapisano ustawienia.")
        messagebox.showinfo("FocusIt", "Ustawienia zapisane.")

    def _on_close(self) -> None:
        if self.session and self.session.active:
            if messagebox.askyesno("FocusIt", "Sesja jest aktywna. "
                                              "Zakończyć ją i przywrócić ustawienia?"):
                self.stop_session(silent=True)
                self.root.destroy()
        else:
            self.root.destroy()


def run_gui() -> None:
    root = tk.Tk()
    FocusItApp(root)
    root.mainloop()
