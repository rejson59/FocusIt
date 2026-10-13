"""FocusIt — interfejs graficzny (Tkinter, ciemny motyw gamingowy)."""

from __future__ import annotations

import copy
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import (FocusSession, FocusStore, ProcessInfo, find_target_pid,
                   get_system_stats, launch_app, list_processes)

BG = "#0B0E14"
PANEL = "#141926"
CARD = "#1B2233"
CARD_HOVER = "#232C42"
TEXT = "#E8ECF4"
MUTED = "#8A94A8"
ACCENT = "#8B5CF6"      # fiolet — kolor marki
GREEN = "#22C55E"       # start / gry
RED = "#EF4444"
GOLD = "#F5C518"

PAGES = [("panel", "🎮  Panel gry"), ("presety", "🎯  Presety"),
         ("procesy", "🧹  Procesy i izolacja"), ("historia", "📊  Historia sesji"),
         ("ustawienia", "⚙️  Ustawienia")]


class FocusItApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.store = FocusStore()
        self.session: FocusSession | None = None
        self.session_started = 0.0
        self.pomodoro_phase = "focus"
        self.pomodoro_left = 0

        root.title("FocusIt — wyciśnij 100% ze swojego komputera")
        root.geometry("1200x780")
        root.minsize(1020, 660)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._style()
        self._build_layout()
        self._show_page("panel")
        self.refresh_targets()
        self.refresh_preset_lists()
        self.refresh_history()
        self._load_settings_to_ui()
        self._tick_stats()
        self.log("Witaj w FocusIt! Wybierz grę, preset i kliknij URUCHOM SESJĘ.")
        self.log("Domyślnie włączona jest SYMULACJA — program tylko pokaże, "
                 "co by zamknął, niczego nie zabijając. Odznacz ją, gdy będziesz gotowy.")

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

        tk.Label(sidebar, text="⚡ FocusIt", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 20, "bold")).pack(pady=(22, 2), padx=18, anchor="w")
        tk.Label(sidebar, text="100% mocy dla Twojej gry", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9)).pack(padx=18, anchor="w")

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
        self._build_presets_page(self.frames["presety"])
        self._build_processes_page(self.frames["procesy"])
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
        self._header(f, "🎮 Panel gry",
                     "Wybierz grę, sprawdź podgląd planu i uruchom sesję. "
                     "FocusIt zamknie wszystko, co nie jest grze potrzebne — "
                     "ale nigdy nie ruszy procesów systemowych Windows.")

        # --- statystyki ---
        stats = tk.Frame(f, bg=BG)
        stats.pack(fill="x", padx=22, pady=6)
        self.stat_labels: dict[str, tk.Label] = {}
        for key, title in [("cpu", "CPU"), ("ram", "RAM"),
                           ("free", "Wolny RAM"), ("procs", "Procesy")]:
            card = tk.Frame(stats, bg=CARD)
            card.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(card, text=title, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(pady=(8, 0))
            lbl = tk.Label(card, text="—", bg=CARD, fg=TEXT,
                           font=("Segoe UI", 15, "bold"))
            lbl.pack(pady=(0, 8))
            self.stat_labels[key] = lbl

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

        # --- log ---
        tk.Label(f, text="Dziennik sesji:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(padx=24, anchor="w")
        self.log_box = tk.Text(f, bg=CARD, fg=TEXT, height=9, relief="flat",
                               font=("Consolas", 9), wrap="word",
                               insertbackground=TEXT)
        self.log_box.pack(fill="both", expand=True, padx=22, pady=(2, 16))

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
        tk.Button(form, text="💾 Zapisz preset", bg=ACCENT, fg="white",
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
                  fg="white", relief="flat", padx=14, pady=6, cursor="hand2",
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
        for var, txt in [
            (self.set_sim, "Domyślnie włączaj SYMULACJĘ przy starcie programu"),
            (self.set_restore_apps, "Po sesji ponownie uruchamiaj zamknięte aplikacje"),
            (self.set_restore_power, "Po sesji przywracaj poprzedni plan zasilania"),
            (self.set_confirm, "Wymagaj potwierdzenia przed trybem IZOLACJI na żywo"),
        ]:
            tk.Checkbutton(f, text=txt, variable=var, bg=BG, fg=TEXT,
                           activebackground=BG, activeforeground=TEXT,
                           selectcolor=CARD, font=("Segoe UI", 10)).pack(
                               padx=22, anchor="w", pady=2)
        tk.Button(f, text="💾 Zapisz ustawienia", bg=ACCENT, fg="white",
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

    def _tick_stats(self) -> None:
        try:
            s = get_system_stats()
            self.stat_labels["cpu"].configure(text=f"{s['cpu_percent']:.0f}%")
            self.stat_labels["ram"].configure(
                text=f"{s['ram_used_gb']:.1f} / {s['ram_total_gb']:.1f} GB")
            self.stat_labels["free"].configure(text=f"{s['ram_available_mb']} MB")
            self.stat_labels["procs"].configure(text=str(s["process_count"]))
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
            self.session_label.configure(
                text=f"⏱ Sesja: {elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}{extra}")
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
        for p in self.store.presets:
            tk.Radiobutton(self.preset_radios,
                           text=f"{p.get('icon', '🎯')} {p['name']}",
                           value=p["name"], variable=self.preset_var,
                           bg=CARD, fg=TEXT, activebackground=CARD_HOVER,
                           activeforeground=TEXT, selectcolor=ACCENT,
                           font=("Segoe UI", 10, "bold"), padx=12, pady=6,
                           indicatoron=False, cursor="hand2",
                           command=self._preset_changed).pack(side="left", padx=4)
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

    # ----------------------------------------------------------------- sesja
    def start_session(self) -> None:
        if self.session and self.session.active:
            return
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

        if preset["mode"] == "isolation" and not simulate and \
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
        self.session_label.configure(text="⏱ Sesja: 00:00:00")
        self.log(f"=== Sesja „{preset['name']}” rozpoczęta ({mode_txt}) ===")
        self.refresh_targets()

    def stop_session(self, silent: bool = False) -> None:
        if not self.session:
            return
        summary = self.session.stop()
        self.store.add_history(summary)
        self.session = None
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.side_status.configure(text="● Brak aktywnej sesji", fg=MUTED)
        self.session_label.configure(text="")
        self.refresh_history()
        self.refresh_targets()
        self.log(f"=== Sesja zakończona. Zamknięte: {summary['killed_count']}, "
                 f"szac. zwolniono: {summary['estimated_freed_mb']:.0f} MB, "
                 f"czas: {summary['duration_sec'] // 60} min ===")
        if not silent:
            messagebox.showinfo(
                "FocusIt — podsumowanie sesji",
                f"Preset: {summary['preset']}\nCel: {summary['target']}\n"
                f"Czas sesji: {summary['duration_sec'] // 60} min "
                f"{summary['duration_sec'] % 60} s\n"
                f"Zamknięte procesy: {summary['killed_count']}\n"
                f"Szacunkowo zwolniony RAM: {summary['estimated_freed_mb']:.0f} MB\n"
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

    # ------------------------------------------------------------- ustawienia
    def _load_settings_to_ui(self) -> None:
        s = self.store.settings
        self.keep_text.delete("1.0", "end")
        self.keep_text.insert("1.0", "\n".join(s.get("keep_always", [])))
        self.set_sim.set(s.get("simulation_by_default", True))
        self.set_restore_apps.set(s.get("restore_apps_after_session", True))
        self.set_restore_power.set(s.get("restore_power_plan", True))
        self.set_confirm.set(s.get("confirm_aggressive_mode", True))

    def _save_settings(self) -> None:
        s = self.store.settings
        s["keep_always"] = [x.strip() for x in
                            self.keep_text.get("1.0", "end").splitlines() if x.strip()]
        s["simulation_by_default"] = self.set_sim.get()
        s["restore_apps_after_session"] = self.set_restore_apps.get()
        s["restore_power_plan"] = self.set_restore_power.get()
        s["confirm_aggressive_mode"] = self.set_confirm.get()
        self.store.save()
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
