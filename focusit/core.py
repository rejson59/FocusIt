"""
FocusIt — silnik programu.

Najważniejsza zasada bezpieczeństwa: FocusIt NIGDY nie zabija procesów,
bez których Windows (lub inny system) nie mógłby poprawnie działać.
Decyzja o zabiciu zapada tylko dla zwykłych procesów użytkownika,
które nie są powiązane z wybraną grą/programem docelowym i nie ma ich
na liście "Zachowaj". Wszystko, czego nie da się jednoznacznie
zidentyfikować (brak dostępu, brak ścieżki), jest BEZPIECZNIE POMIJANE.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

import psutil

APP_NAME = "FocusIt"

# ---------------------------------------------------------------------------
# Listy ochronne — procesy, których NIE WOLNO zabijać
# ---------------------------------------------------------------------------

# Procesy krytyczne Windows / jądra / logowania / bezpieczeństwa.
HARD_PROTECTED_NAMES = {
    "system", "system idle process", "registry", "secure system",
    "memory compression", "system interrupts", "idle",
    "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "lsalso.exe", "svchost.exe",
    "spoolsv.exe", "fontdrvhost.exe", "dwm.exe", "audiodg.exe",
    "msmpeng.exe", "nissrv.exe", "securityhealthservice.exe",
    "sgrmbroker.exe", "wudfhost.exe", "dashost.exe", "lsm.exe",
    "searchindexer.exe", "searchprotocolhost.exe", "searchfilterhost.exe",
    "wmiprvse.exe", "trustedinstaller.exe", "tiworker.exe",
    "vssvc.exe", "winresume.exe", "smss", "csrss",
    # Linux / POSIX (gdy program działa poza Windows)
    "systemd", "init", "kthreadd", "launchd", "kernel_task",
}

# Powłoka i obsługa pulpitu / wejścia — zabicie ich psuje obsługę komputera.
SHELL_ESSENTIAL_NAMES = {
    "explorer.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe",
    "searchhost.exe", "searchapp.exe", "textinputhost.exe", "ctfmon.exe",
    "runtimebroker.exe", "applicationframehost.exe", "lockapp.exe",
    "logonui.exe", "dllhost.exe", "consent.exe", "taskhostw.exe",
    "taskhost.exe", "sihost.exe", "conhost.exe", "chsime.exe",
    "smartscreen.exe", "securityhealthsystray.exe", "shellexperiencehost",
}

# Serwisy sterowników GPU / audio — potrzebne, żeby gra działała poprawnie.
DRIVER_NAMES = {
    "nvcontainer.exe", "nvdisplay.container.exe", "nvsphelper64.exe",
    "amdrsserv.exe", "atiesrxx.exe", "atieclxx.exe", "radeonsettings.exe",
    "igfxcuservice.exe", "igfxem.exe", "igfxtray.exe", "intelgraphicssoftware.exe",
    "rtkauduservice.exe", "rtkauduservice64.exe", "nahimicservice.exe",
    "nvbackend.exe", "presentmonservice.exe",
}

SYSTEM_USERS_HINTS = ("system", "local service", "network service", "usługa lokalna")
WINDOWS_DIR_RE = re.compile(r"^[a-z]:\\windows(\\|$)")
GUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

HIGH_PERFORMANCE_GUIDS = [
    "e9a42b02-d5df-448d-aa00-03f14749eb61",  # Wydajność maksymalna (Ultimate)
    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",  # Wysoka wydajność
]

# ---------------------------------------------------------------------------
# Presety startowe
# ---------------------------------------------------------------------------

DEFAULT_PRESETS = [
    {
        "name": "Gry",
        "icon": "🎮",
        "description": "Tryb główny: maksymalna wydajność dla wybranej gry.",
        "mode": "isolation",
        "close_apps": ["chrome.exe", "firefox.exe", "spotify.exe", "discord.exe"],
        "launch_apps": [],
        "keep_apps": ["steam.exe", "epicgameslauncher.exe", "discord.exe",
                      "nvcontainer.exe", "obs64.exe"],
        "power_high_performance": True,
        "raise_priority": True,
        "pomodoro_minutes": 0,
        "built_in": True,
    },
    {
        "name": "Nauka",
        "icon": "📚",
        "description": "Skupienie: zamyka rozpraszacze i włącza timer Pomodoro.",
        "mode": "gentle",
        "close_apps": ["steam.exe", "epicgameslauncher.exe", "spotify.exe",
                       "discord.exe", "chrome.exe"],
        "launch_apps": [],
        "keep_apps": [],
        "power_high_performance": False,
        "raise_priority": False,
        "pomodoro_minutes": 25,
        "built_in": True,
    },
    {
        "name": "Praca",
        "icon": "💼",
        "description": "Zamknięcie prywatnych rozpraszaczy na czas pracy.",
        "mode": "gentle",
        "close_apps": ["steam.exe", "spotify.exe"],
        "launch_apps": [],
        "keep_apps": [],
        "power_high_performance": False,
        "raise_priority": False,
        "pomodoro_minutes": 50,
        "built_in": True,
    },
    {
        "name": "Tworzenie",
        "icon": "🎬",
        "description": "Montaż / streaming / programowanie z wysokim priorytetem.",
        "mode": "gentle",
        "close_apps": ["chrome.exe", "steam.exe"],
        "launch_apps": [],
        "keep_apps": ["obs64.exe"],
        "power_high_performance": True,
        "raise_priority": True,
        "pomodoro_minutes": 0,
        "built_in": True,
    },
]

DEFAULT_SETTINGS = {
    "simulation_by_default": True,
    "restore_apps_after_session": True,
    "restore_power_plan": True,
    "keep_always": ["discord.exe"],
    "confirm_aggressive_mode": True,
    "auto_session": False,          # wykrywaj start gry z biblioteki i sam startuj sesję
    "auto_stop": True,              # kończ auto-sesję, gdy gra zostanie zamknięta
    "show_session_widget": True,    # mini-widget podczas sesji
    "autostart_backup": {},         # kopie wyłączonych wpisów autostartu
    "hotkey_enabled": True,         # Ctrl+Alt+F startuje/kończy sesję
    "check_updates": True,          # sprawdzaj nowe wersje na GitHubie
    "onboarded": False,             # czy pokazano ekran powitalny
}


# ---------------------------------------------------------------------------
# Dane
# ---------------------------------------------------------------------------

@dataclass
class ProcessInfo:
    pid: int
    ppid: int = 0
    name: str = ""
    exe: str = ""
    username: str = ""
    status: str = ""
    memory_mb: float = 0.0
    create_time: float = 0.0

    @property
    def stem(self) -> str:
        return Path(self.name).stem.lower() if self.name else ""


@dataclass
class Decision:
    proc: ProcessInfo
    action: str            # "kill" | "keep"
    reason: str
    category: str          # np. "System", "Cel", "Zachowaj", "Do zabicia"

    @property
    def kill(self) -> bool:
        return self.action == "kill"


@dataclass
class KillPlan:
    decisions: list[Decision] = field(default_factory=list)

    @property
    def kill_list(self) -> list[Decision]:
        return [d for d in self.decisions if d.kill]

    @property
    def keep_list(self) -> list[Decision]:
        return [d for d in self.decisions if not d.kill]

    @property
    def estimated_freed_mb(self) -> float:
        return round(sum(d.proc.memory_mb for d in self.kill_list), 1)

    def summary(self) -> str:
        return (f"Do zamknięcia: {len(self.kill_list)} procesów "
                f"(~{self.estimated_freed_mb:.0f} MB RAM), "
                f"zachowane: {len(self.keep_list)}.")


@dataclass
class ExecutionResult:
    killed: list[ProcessInfo] = field(default_factory=list)
    suspended: list[ProcessInfo] = field(default_factory=list)
    simulated: list[ProcessInfo] = field(default_factory=list)
    failed: list[tuple[ProcessInfo, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pobieranie procesów i statystyk
# ---------------------------------------------------------------------------

def list_processes() -> list[ProcessInfo]:
    out: list[ProcessInfo] = []
    for p in psutil.process_iter(["pid", "ppid", "name", "exe", "username",
                                  "status", "memory_info", "create_time"]):
        try:
            info = p.info
            mem = info.get("memory_info")
            out.append(ProcessInfo(
                pid=info["pid"],
                ppid=info.get("ppid") or 0,
                name=info.get("name") or "",
                exe=info.get("exe") or "",
                username=info.get("username") or "",
                status=info.get("status") or "",
                memory_mb=round(mem.rss / (1024 * 1024), 1) if mem else 0.0,
                create_time=info.get("create_time") or 0.0,
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    out.sort(key=lambda x: x.memory_mb, reverse=True)
    return out


def get_system_stats() -> dict:
    vm = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.15),
        "ram_percent": vm.percent,
        "ram_used_gb": round(vm.used / (1024 ** 3), 2),
        "ram_total_gb": round(vm.total / (1024 ** 3), 2),
        "ram_available_mb": round(vm.available / (1024 * 1024)),
        "process_count": len(psutil.pids()),
    }


# ---------------------------------------------------------------------------
# Klasyfikacja bezpieczeństwa
# ---------------------------------------------------------------------------

def _norm_path(path: str) -> str:
    return (path or "").replace("/", "\\").lower().strip('"')


def is_system_path(exe: str) -> bool:
    p = _norm_path(exe)
    if not p:
        return False
    if WINDOWS_DIR_RE.match(p) or "\\system32\\" in p or "\\syswow64\\" in p:
        return True
    # POSIX: katalogi systemowe
    return p.startswith(("/usr/lib/systemd/", "/sbin/", "/usr/sbin/",
                         "/system/library/", "/usr/libexec/"))


def is_hard_protected(proc: ProcessInfo) -> Optional[str]:
    """Powód ochrony bezwzględnej albo None, jeśli proces nie jest krytyczny."""
    name = (proc.name or "").lower()
    if proc.pid <= 4:
        return "proces jądra systemu (PID ≤ 4)"
    if name in HARD_PROTECTED_NAMES:
        return "krytyczny proces systemowy"
    if name in SHELL_ESSENTIAL_NAMES:
        return "powłoka / obsługa pulpitu i klawiatury"
    if name in DRIVER_NAMES:
        return "sterownik GPU/audio — potrzebny grze"
    if is_system_path(proc.exe):
        return "plik w katalogu systemowym Windows"
    if name.startswith("systemd-") or name.startswith("kworker") or \
            name.startswith("ksoftirqd"):
        return "usługa systemowa / wątek jądra"
    user = (proc.username or "").lower()
    if user and any(h in user for h in SYSTEM_USERS_HINTS) and (
            user.endswith("system") or "service" in user):
        # konta usług systemowych; zwykły użytkownik to np. DESKTOP\Jan
        if "\\" in user or user in ("nt authority\\system",):
            return f"konto systemowe ({proc.username})"
    if not proc.exe:
        return "brak dostępu do ścieżki — bezpiecznie pominięto"
    if proc.status == psutil.STATUS_ZOMBIE:
        return "proces zombie"
    return None


def _related_pids(processes: list[ProcessInfo], target_pids: set[int],
                  own_pid: int) -> set[int]:
    by_pid = {p.pid: p for p in processes}
    children: dict[int, list[int]] = {}
    for p in processes:
        children.setdefault(p.ppid, []).append(p.pid)

    related: set[int] = set()

    def add_descendants(pid: int) -> None:
        stack = [pid]
        while stack:
            cur = stack.pop()
            if cur in related:
                continue
            related.add(cur)
            stack.extend(children.get(cur, []))

    def add_ancestors(pid: int) -> None:
        cur = pid
        seen = set()
        while cur and cur in by_pid and cur not in seen:
            seen.add(cur)
            related.add(cur)
            cur = by_pid[cur].ppid

    for pid in target_pids:
        add_ancestors(pid)      # np. launcher, który uruchomił grę
        add_descendants(pid)    # np. anti-cheat / pomocnicze procesy gry
    # FocusIt i wszystko, co sam uruchomił (w tym gra startowana z aplikacji)
    add_ancestors(own_pid)
    add_descendants(own_pid)
    related.add(own_pid)
    return related


def compute_plan(processes: list[ProcessInfo],
                 target_pid: Optional[int] = None,
                 target_exe: str = "",
                 target_name: str = "",
                 mode: str = "isolation",
                 close_names: Iterable[str] = (),
                 keep_names: Iterable[str] = (),
                 own_pid: Optional[int] = None,
                 current_username: Optional[str] = None) -> KillPlan:
    """
    Buduje plan: co zamknąć, a co zachować — wraz z uzasadnieniem każdej decyzji.

    mode="isolation"  → zabijaj każdy niepowiązany proces użytkownika
    mode="gentle"     → zamykaj tylko procesy z listy close_names
    """
    own_pid = own_pid if own_pid is not None else os.getpid()
    if current_username is None:
        try:
            current_username = psutil.Process(own_pid).username()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            current_username = ""
    current_user_key = (current_username or "").replace("/", "\\").rsplit("\\", 1)[-1].lower()
    close_set = {Path(c.strip().lower()).stem for c in close_names if c.strip()}
    keep_set = {Path(c.strip().lower()).stem for c in keep_names if c.strip()}
    target_exe_norm = _norm_path(target_exe)
    target_stem = Path((target_name or target_exe).replace("\\", "/")).stem.lower()

    target_pids: set[int] = set()
    for p in processes:
        if target_pid and p.pid == target_pid:
            target_pids.add(p.pid)
        if target_exe_norm and _norm_path(p.exe) == target_exe_norm:
            target_pids.add(p.pid)
        if target_stem and p.stem == target_stem:
            target_pids.add(p.pid)

    target_dirs = {_norm_path(p.exe).rsplit("\\", 1)[0]
                   for p in processes if p.pid in target_pids and p.exe}
    related = _related_pids(processes, target_pids, own_pid)

    decisions: list[Decision] = []
    for p in processes:
        # 1) Cel i wszystko z nim powiązane
        if p.pid in target_pids:
            decisions.append(Decision(p, "keep", "wybrana gra/program (cel sesji)", "Cel"))
            continue
        if p.pid in related:
            reason = ("proces FocusIt" if p.pid == own_pid
                      else "powiązany z celem (launcher / proces potomny / ten sam folder gry)"
                      if target_dirs and _norm_path(p.exe).rsplit("\\", 1)[0] in target_dirs and p.exe
                      else "powiązany z celem lub z FocusIt (proces nadrzędny/potomny)")
            decisions.append(Decision(p, "keep", reason, "Powiązany"))
            continue
        if target_dirs and p.exe and _norm_path(p.exe).rsplit("\\", 1)[0] in target_dirs:
            decisions.append(Decision(p, "keep",
                                      "ten sam folder co gra (np. anti-cheat, helper)",
                                      "Powiązany"))
            continue
        # 2) Lista "Zachowaj"
        if p.stem in keep_set:
            decisions.append(Decision(p, "keep", "lista „Zachowaj” użytkownika", "Zachowaj"))
            continue
        # 3) Ochrona bezwzględna
        protected = is_hard_protected(p)
        if protected:
            decisions.append(Decision(p, "keep", protected, "Chroniony"))
            continue
        # 3b) Nigdy nie zamykamy procesów innego użytkownika (np. usług root/SYSTEM
        #     ani programów drugiej zalogowanej osoby) — tylko własne procesy.
        proc_user_key = (p.username or "").replace("/", "\\").rsplit("\\", 1)[-1].lower()
        if current_user_key and proc_user_key and proc_user_key != current_user_key:
            decisions.append(Decision(
                p, "keep",
                f"proces innego użytkownika ({p.username}) — zamykamy tylko własne",
                "Chroniony"))
            continue
        # 4) Decyzja wg trybu
        if mode == "gentle":
            if p.stem in close_set:
                decisions.append(Decision(p, "kill",
                                          "na liście zamykanych aplikacji presetu",
                                          "Do zamknięcia"))
            else:
                decisions.append(Decision(p, "keep",
                                          "tryb łagodny: nie ma go na liście zamykania",
                                          "Zachowaj"))
        else:  # isolation
            decisions.append(Decision(p, "kill",
                                      "proces użytkownika niezwiązany z celem sesji",
                                      "Do zamknięcia"))
    decisions.sort(key=lambda d: (not d.kill, -d.proc.memory_mb))
    return KillPlan(decisions)


# ---------------------------------------------------------------------------
# Wykonywanie planu (z ponowną weryfikacją tuż przed zamknięciem)
# ---------------------------------------------------------------------------

def execute_plan(plan: KillPlan, simulate: bool = True,
                 log: Callable[[str], None] = print,
                 freeze: bool = False) -> ExecutionResult:
    result = ExecutionResult()
    candidates = [d.proc for d in plan.kill_list]
    if simulate:
        result.simulated = candidates
        verb = "zamroziłbym" if freeze else "zamknąłbym"
        for p in candidates:
            log(f"[SYMULACJA] {verb}: {p.name} (PID {p.pid}, {p.memory_mb:.0f} MB)")
        return result
    if freeze:
        # zamrożenie zamiast zabijania: procesy nie tracą stanu i wracają po sesji
        result.suspended = suspend_processes(candidates, log=log)
        done = {p.pid for p in result.suspended}
        result.failed = [(p, "nie udało się zamrozić")
                         for p in candidates if p.pid not in done]
        return result

    live: list[psutil.Process] = []
    for info in candidates:
        try:
            proc = psutil.Process(info.pid)
            # Weryfikacja przed zamknięciem: czy to nadal ten sam proces
            # (ochrona przed ponownym użyciem PID) i czy nie stał się krytyczny.
            if abs((proc.create_time() or 0) - (info.create_time or 0)) > 1.0:
                log(f"Pominięto {info.name}: PID został ponownie użyty.")
                continue
            fresh = ProcessInfo(pid=proc.pid, name=proc.name(),
                                exe=(proc.exe() if proc.is_running() else "") or "",
                                username="", status="", create_time=info.create_time)
            if is_hard_protected(fresh) and fresh.exe:
                # svchost itp. mają exe w System32 — podwójne zabezpieczenie
                if fresh.name.lower() in HARD_PROTECTED_NAMES or is_system_path(fresh.exe):
                    log(f"Pominięto {info.name}: proces chroniony.")
                    continue
            proc.terminate()  # grzeczna prośba o zamknięcie (jak kliknięcie X)
            live.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            result.failed.append((info, str(exc)))

    if live:
        _, alive = psutil.wait_procs(live, timeout=3)
        for proc in alive:  # tylko uporczywe procesy dostają kill()
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if alive:
            psutil.wait_procs(alive, timeout=2)

    for info in candidates:
        if not psutil.pid_exists(info.pid):
            result.killed.append(info)
            log(f"Zamknięto: {info.name} (zwolniono ~{info.memory_mb:.0f} MB)")
        elif info not in [f[0] for f in result.failed]:
            # proces mógł zmienić PID-check; raportuj tylko realne porażki
            try:
                if psutil.Process(info.pid).create_time() == info.create_time:
                    result.failed.append((info, "proces nie dał się zamknąć"))
            except psutil.NoSuchProcess:
                result.killed.append(info)
    return result


# ---------------------------------------------------------------------------
# Plan zasilania (Windows) i priorytet procesu
# ---------------------------------------------------------------------------

class PowerPlanManager:
    """Przełącza plan zasilania Windows i przywraca poprzedni. Poza Windows: no-op."""

    def __init__(self) -> None:
        self._previous_guid: Optional[str] = None
        self.is_windows = sys.platform.startswith("win")

    def current_guid(self) -> Optional[str]:
        if not self.is_windows:
            return None
        try:
            out = subprocess.run(["powercfg", "/getactivescheme"],
                                 capture_output=True, text=True, timeout=10).stdout
            m = GUID_RE.search(out)
            return m.group(0) if m else None
        except Exception:
            return None

    def set_high_performance(self) -> str:
        if not self.is_windows:
            return "Plan zasilania: pominięto (tylko Windows)."
        self._previous_guid = self.current_guid()
        for guid in HIGH_PERFORMANCE_GUIDS:
            try:
                r = subprocess.run(["powercfg", "/setactive", guid],
                                   capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    return f"Plan zasilania: włączono wysoką wydajność ({guid[:8]}…)."
            except Exception:
                pass
        return "Plan zasilania: nie udało się zmienić (brak planu wysokiej wydajności)."

    def restore(self) -> str:
        if not self.is_windows or not self._previous_guid:
            return "Plan zasilania: brak zmian do przywrócenia."
        try:
            subprocess.run(["powercfg", "/setactive", self._previous_guid],
                           capture_output=True, timeout=10)
            return "Plan zasilania: przywrócono poprzedni."
        except Exception:
            return "Plan zasilania: nie udało się przywrócić poprzedniego."
        finally:
            self._previous_guid = None

    def restore_to(self, guid: str) -> str:
        """Przywraca konkretny plan zasilania (używane po awarii programu)."""
        if not self.is_windows or not guid:
            return "Plan zasilania: brak zapisanego planu do przywrócenia."
        try:
            subprocess.run(["powercfg", "/setactive", guid],
                           capture_output=True, timeout=10)
            return "Plan zasilania: przywrócono plan sprzed przerwanej sesji."
        except Exception:
            return "Plan zasilania: nie udało się przywrócić zapisanego planu."


def set_target_priority(pid: int, high: bool = True) -> str:
    try:
        proc = psutil.Process(pid)
        if sys.platform.startswith("win"):
            proc.nice(psutil.HIGH_PRIORITY_CLASS if high else psutil.NORMAL_PRIORITY_CLASS)
        else:
            proc.nice(-5 if high else 0)
        return f"Priorytet {'wysoki' if high else 'normalny'} dla PID {pid}."
    except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError) as exc:
        return f"Priorytet: nie udało się zmienić ({exc})."


def launch_app(path_or_name: str) -> str:
    """Uruchamia aplikację po ścieżce albo nazwie (szuka w PATH / startuje przez shell)."""
    target = (path_or_name or "").strip().strip('"')
    if not target:
        return ""
    try:
        if Path(target).exists():
            if sys.platform.startswith("win"):
                os.startfile(target)  # type: ignore[attr-defined]
            else:
                subprocess.Popen([target])
            return f"Uruchomiono: {target}"
        found = shutil.which(target)
        if found:
            subprocess.Popen([found])
            return f"Uruchomiono: {target}"
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
            return f"Uruchomiono (przez system): {target}"
        return f"Nie znaleziono aplikacji: {target}"
    except Exception as exc:
        return f"Błąd uruchamiania {target}: {exc}"


def find_target_pid(exe_path: str = "", name: str = "") -> Optional[int]:
    stem = Path((name or exe_path).replace("\\", "/")).stem.lower()
    exe_norm = _norm_path(exe_path)
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            if exe_norm and _norm_path(p.info.get("exe") or "") == exe_norm:
                return p.info["pid"]
            if stem and Path(p.info.get("name") or "").stem.lower() == stem:
                return p.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


# ---------------------------------------------------------------------------
# Sesja FocusIt
# ---------------------------------------------------------------------------

class FocusSession:
    def __init__(self, preset: dict, settings: dict,
                 target_pid: Optional[int] = None,
                 target_exe: str = "", target_name: str = "",
                 log: Callable[[str], None] = print) -> None:
        self.preset = preset
        self.settings = settings
        self.target_pid = target_pid
        self.target_exe = target_exe
        self.target_name = target_name or Path(target_exe.replace("\\", "/")).name
        self.log = log
        self.power = PowerPlanManager()
        self.active = False
        self.started_at = 0.0
        self.plan: Optional[KillPlan] = None
        self.result: Optional[ExecutionResult] = None
        self.ram_before_mb = 0
        self._priority_pids: list[int] = []
        self.simulate = True

    def build_plan(self, processes: Optional[list[ProcessInfo]] = None) -> KillPlan:
        processes = processes if processes is not None else list_processes()
        keep = set(self.preset.get("keep_apps", [])) | set(self.settings.get("keep_always", []))
        self.plan = compute_plan(
            processes,
            target_pid=self.target_pid,
            target_exe=self.target_exe,
            target_name=self.target_name,
            mode=self.preset.get("mode", "isolation"),
            close_names=self.preset.get("close_apps", []),
            keep_names=keep,
        )
        return self.plan

    def start(self, simulate: bool) -> ExecutionResult:
        self.simulate = simulate
        stats = get_system_stats()
        self.ram_before_mb = stats["ram_available_mb"]
        self.processes_before = stats["process_count"]
        if self.plan is None:
            self.build_plan()
        self.log(f"Plan sesji „{self.preset.get('name')}”: {self.plan.summary()}")
        self.result = execute_plan(
            self.plan, simulate=simulate, log=self.log,
            freeze=bool(self.preset.get("freeze_processes")))

        if not simulate:
            if self.preset.get("power_high_performance"):
                self.log(self.power.set_high_performance())
            # uruchom aplikacje z presetu (poza celem — cel startuje osobno)
            for app in self.preset.get("launch_apps", []):
                if Path(app.replace("\\", "/")).stem.lower() != Path(
                        self.target_name.replace("\\", "/")).stem.lower():
                    self.log(launch_app(app))
            if self.preset.get("raise_priority"):
                pid = self.target_pid or find_target_pid(self.target_exe, self.target_name)
                if pid:
                    self.target_pid = pid
                    self._priority_pids = [pid]
                    self.log(set_target_priority(pid, high=True))
                else:
                    self.log("Priorytet: nie znaleziono uruchomionego procesu celu "
                             "(ustawię go, gdy gra będzie znana przy starcie).")
            affinity = self.preset.get("cpu_affinity") or []
            if affinity:
                pid = self.target_pid or find_target_pid(self.target_exe,
                                                         self.target_name)
                if pid:
                    self.log(set_cpu_affinity(pid, list(affinity)))
        self.active = True
        self.started_at = time.time()
        return self.result

    def stop(self) -> dict:
        duration = int(time.time() - self.started_at) if self.started_at else 0
        restored = []
        if self.active and not self.simulate:
            if self.result and self.result.suspended:
                n = resume_processes([p.pid for p in self.result.suspended],
                                     log=self.log)
                self.log(f"Odmrożono {n} procesów po sesji.")
            for pid in self._priority_pids:
                self.log(set_target_priority(pid, high=False))
            if self.preset.get("power_high_performance") and \
                    self.settings.get("restore_power_plan", True):
                self.log(self.power.restore())
            if self.settings.get("restore_apps_after_session", True) and self.result:
                seen = set()
                for info in self.result.killed:
                    exe = info.exe
                    if exe and Path(exe).exists() and exe.lower() not in seen:
                        seen.add(exe.lower())
                        msg = launch_app(exe)
                        restored.append(info.name)
                        self.log(f"Przywracanie: {msg}")
        ram_after = get_system_stats()["ram_available_mb"]
        summary = {
            "preset": self.preset.get("name", "?"),
            "target": self.target_name or "(brak)",
            "duration_sec": duration,
            "killed_count": len(self.result.killed) if self.result else 0,
            "suspended_count": len(self.result.suspended) if self.result else 0,
            "simulated_count": len(self.result.simulated) if self.result else 0,
            "failed_count": len(self.result.failed) if self.result else 0,
            "estimated_freed_mb": self.plan.estimated_freed_mb if self.plan else 0,
            "ram_available_before_mb": self.ram_before_mb,
            "ram_available_after_mb": ram_after,
            "processes_before": getattr(self, "processes_before", 0),
            "processes_after": get_system_stats()["process_count"],
            "restored_apps": restored,
            "simulate": self.simulate,
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.active = False
        return summary

    def state_dict(self) -> dict:
        """Stan aktywnej sesji do odzyskiwania po awarii FocusIt."""
        return {
            "preset": self.preset.get("name", "?"),
            "target": self.target_name,
            "started_at": self.started_at,
            "killed_exes": [p.exe for p in (self.result.killed if self.result else [])
                            if p.exe],
            "suspended_pids": [p.pid for p in
                               (self.result.suspended if self.result else [])],
            "power_guid": self.power._previous_guid,
        }


# ---------------------------------------------------------------------------
# Zapis ustawień / presetów / historii
# ---------------------------------------------------------------------------

def app_data_dir() -> Path:
    override = os.environ.get("FOCUSIT_HOME")
    if override:
        p = Path(override)
    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        p = Path(base) / APP_NAME
    else:
        p = Path.home() / ".focusit"
    p.mkdir(parents=True, exist_ok=True)
    return p


class FocusStore:
    def __init__(self, directory: Optional[Path] = None) -> None:
        self.dir = directory or app_data_dir()
        self.config_file = self.dir / "config.json"
        self.history_file = self.dir / "history.json"
        self.presets: list[dict] = copy.deepcopy(DEFAULT_PRESETS)
        self.settings: dict = copy.deepcopy(DEFAULT_SETTINGS)
        self.game_profiles: dict = {}   # exe (małe litery) -> {mode, keep_apps, close_apps}
        self.load()

    def load(self) -> None:
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                if data.get("presets"):
                    self.presets = data["presets"]
                self.settings.update(data.get("settings", {}))
                self.game_profiles = data.get("game_profiles", {})
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        self.config_file.write_text(
            json.dumps({"presets": self.presets, "settings": self.settings,
                        "game_profiles": self.game_profiles},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    def game_profile(self, exe: str) -> dict:
        return self.game_profiles.get((exe or "").lower(), {})

    def set_game_profile(self, exe: str, profile: dict) -> None:
        if exe:
            self.game_profiles[exe.lower()] = profile
            self.save()

    def get_preset(self, name: str) -> Optional[dict]:
        return next((p for p in self.presets if p["name"] == name), None)

    def upsert_preset(self, preset: dict) -> None:
        for i, p in enumerate(self.presets):
            if p["name"] == preset["name"]:
                self.presets[i] = preset
                self.save()
                return
        self.presets.append(preset)
        self.save()

    def delete_preset(self, name: str) -> bool:
        p = self.get_preset(name)
        if not p or p.get("built_in"):
            return False
        self.presets = [x for x in self.presets if x["name"] != name]
        self.save()
        return True

    # --- stan przerwanej sesji (odzyskiwanie po awarii) ---
    @property
    def session_state_file(self) -> Path:
        return self.dir / "session_state.json"

    def save_session_state(self, state: dict) -> None:
        try:
            self.session_state_file.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def load_session_state(self) -> dict:
        if self.session_state_file.exists():
            try:
                return json.loads(self.session_state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def clear_session_state(self) -> None:
        try:
            self.session_state_file.unlink(missing_ok=True)
        except OSError:
            pass

    def add_history(self, entry: dict) -> None:
        history = self.load_history()
        history.insert(0, entry)
        self.history_file.write_text(
            json.dumps(history[:200], ensure_ascii=False, indent=2), encoding="utf-8")

    def load_history(self) -> list[dict]:
        if self.history_file.exists():
            try:
                return json.loads(self.history_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return []
        return []


# ---------------------------------------------------------------------------
# Biblioteka gier (Steam / Epic / GOG)
# ---------------------------------------------------------------------------

@dataclass
class GameEntry:
    name: str
    exe: str
    platform: str               # Steam / Epic / GOG / Ręcznie
    appid: str = ""
    image: str = ""             # ścieżka do okładki (jeśli istnieje lokalnie)

    @property
    def stem(self) -> str:
        return Path(self.exe.replace("\\", "/")).stem.lower()


def parse_acf(text: str) -> dict:
    """Parsuje pliki .acf / .vdf Steama (proste pary klucz-wartość)."""
    pairs = re.findall(r'"([^"]+)"\s+"([^"]*)"', text or "")
    return {k.lower(): v for k, v in pairs}


def _largest_exe(folder: Path) -> str:
    try:
        exes = [p for p in folder.glob("*.exe") if p.is_file()]
        if not exes:
            exes = [p for p in folder.glob("*/*.exe") if p.is_file()]
        if not exes:
            return ""
        return str(max(exes, key=lambda p: p.stat().st_size))
    except OSError:
        return ""


def _steam_base_paths() -> list[Path]:
    bases: list[Path] = []
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Valve\Steam") as key:
                bases.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except Exception:
            pass
        for guess in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
            bases.append(Path(guess))
    return [b for b in bases if b.exists()]


def scan_steam_games() -> list[GameEntry]:
    games: list[GameEntry] = []
    for base in _steam_base_paths():
        libraries = [base]
        vdf = base / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                data = parse_acf(vdf.read_text(encoding="utf-8", errors="ignore"))
                for key, value in data.items():
                    if key == "path":
                        libraries.append(Path(value))
            except OSError:
                pass
        for lib in libraries:
            steamapps = lib / "steamapps"
            if not steamapps.exists():
                continue
            for manifest in steamapps.glob("appmanifest_*.acf"):
                try:
                    info = parse_acf(manifest.read_text(encoding="utf-8",
                                                        errors="ignore"))
                except OSError:
                    continue
                name = info.get("name", "")
                installdir = info.get("installdir", "")
                appid = info.get("appid", "")
                if not name or not installdir:
                    continue
                folder = steamapps / "common" / installdir
                exe = _largest_exe(folder) if folder.exists() else ""
                image = ""
                cache = base / "appcache" / "librarycache" / f"{appid}_library_600x900.jpg"
                if appid and cache.exists():
                    image = str(cache)
                games.append(GameEntry(name=name, exe=exe, platform="Steam",
                                       appid=appid, image=image))
    return games


def parse_epic_manifest(data: dict) -> Optional[GameEntry]:
    name = data.get("DisplayName") or ""
    location = data.get("InstallLocation") or ""
    launch = data.get("LaunchExecutable") or ""
    if not name:
        return None
    exe = str(Path(location) / launch) if location and launch else ""
    # jeśli folder gry istnieje, a wskazany plik nie — weź największy .exe z folderu
    if location and Path(location).exists() and exe and not Path(exe).exists():
        exe = _largest_exe(Path(location))
    return GameEntry(name=name, exe=exe, platform="Epic")


def scan_epic_games() -> list[GameEntry]:
    games: list[GameEntry] = []
    manifests = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / \
        "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if manifests.exists():
        for item in manifests.glob("*.item"):
            try:
                entry = parse_epic_manifest(
                    json.loads(item.read_text(encoding="utf-8", errors="ignore")))
            except (OSError, json.JSONDecodeError):
                continue
            if entry:
                games.append(entry)
    return games


def scan_gog_games() -> list[GameEntry]:
    games: list[GameEntry] = []
    for root in (r"C:\Program Files (x86)\GOG Galaxy\Games",
                 r"C:\Program Files\GOG Galaxy\Games", r"C:\GOG Games"):
        base = Path(root)
        if base.exists():
            for folder in sorted(p for p in base.iterdir() if p.is_dir()):
                games.append(GameEntry(name=folder.name,
                                       exe=_largest_exe(folder), platform="GOG"))
    return games


def scan_game_library() -> list[GameEntry]:
    """Wszystkie wykryte gry, bez duplikatów, posortowane po nazwie."""
    found: list[GameEntry] = []
    for scanner in (scan_steam_games, scan_epic_games, scan_gog_games):
        try:
            found.extend(scanner())
        except Exception:
            pass
    unique: dict[str, GameEntry] = {}
    for g in found:
        key = (g.exe or g.name).lower()
        if key not in unique and g.name:
            unique[key] = g
    return sorted(unique.values(), key=lambda g: g.name.lower())


# ---------------------------------------------------------------------------
# GPU (NVIDIA przez nvidia-smi, jeśli dostępne)
# ---------------------------------------------------------------------------

def get_gpu_stats() -> Optional[dict]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name"],
            capture_output=True, text=True, timeout=6).stdout.strip().splitlines()
        if not out:
            return None
        parts = [p.strip() for p in out[0].split(",")]
        return {"percent": float(parts[0]), "mem_used_mb": float(parts[1]),
                "mem_total_mb": float(parts[2]), "temp_c": float(parts[3]),
                "name": parts[4] if len(parts) > 4 else "NVIDIA"}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Czyszczenie plików tymczasowych (tylko folder temp użytkownika)
# ---------------------------------------------------------------------------

def _temp_dirs(dirs: Optional[list[Path]] = None) -> list[Path]:
    if dirs is not None:
        return dirs
    import tempfile
    return [Path(tempfile.gettempdir())]


def preview_temp_clean(dirs: Optional[list[Path]] = None,
                       older_than_hours: int = 24) -> dict:
    cutoff = time.time() - older_than_hours * 3600
    count = size = 0
    for base in _temp_dirs(dirs):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    count += 1
                    size += p.stat().st_size
            except OSError:
                continue
    return {"files": count, "size_mb": round(size / (1024 * 1024), 1),
            "older_than_hours": older_than_hours}


def execute_temp_clean(dirs: Optional[list[Path]] = None,
                       older_than_hours: int = 24) -> dict:
    cutoff = time.time() - older_than_hours * 3600
    removed = failed = freed = 0
    for base in _temp_dirs(dirs):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    freed += p.stat().st_size
                    p.unlink()
                    removed += 1
            except OSError:
                failed += 1
    return {"removed": removed, "failed": failed,
            "freed_mb": round(freed / (1024 * 1024), 1)}


# ---------------------------------------------------------------------------
# Autostart Windows (rejestr Run) — wyłączanie jest w pełni odwracalne
# ---------------------------------------------------------------------------

_AUTOSTART_KEYS = [("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
                   ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Run")]


def list_autostart() -> list[dict]:
    entries: list[dict] = []
    if not sys.platform.startswith("win"):
        return entries
    try:
        import winreg
    except ImportError:
        return entries
    hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    for hive_name, subkey in _AUTOSTART_KEYS:
        try:
            with winreg.OpenKey(hives[hive_name], subkey) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        entries.append({"name": name, "command": str(value),
                                        "hive": hive_name, "subkey": subkey})
                        i += 1
                    except OSError:
                        break
        except OSError:
            continue
    return entries


def set_autostart_enabled(entry: dict, enabled: bool) -> bool:
    """enabled=False usuwa wpis (kopia zapasowa trafia do ustawień FocusIt)."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg
        hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}
        with winreg.OpenKey(hives[entry["hive"]], entry["subkey"], 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, entry["name"], 0, winreg.REG_SZ,
                                  entry["command"])
            else:
                winreg.DeleteValue(key, entry["name"])
        return True
    except OSError:
        return False


def create_restore_point(description: str = "FocusIt - przed sesja optymalizacji") -> str:
    if not sys.platform.startswith("win"):
        return "Punkt przywracania: dostępne tylko w Windows."
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Checkpoint-Computer -Description '{description}' -RestorePointType 'MODIFY_SETTINGS'"],
            capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            return "Punkt przywracania: utworzono."
        return ("Punkt przywracania: nie udało się (uruchom FocusIt jako "
                "administrator; Windows pozwala na 1 punkt na 24 h).")
    except Exception as exc:
        return f"Punkt przywracania: błąd ({exc})."


# ---------------------------------------------------------------------------
# v1.2: zamrażanie procesów, powinowactwo CPU, aktualizacje, odzyskiwanie
# ---------------------------------------------------------------------------

def parse_affinity(text: str) -> list[int]:
    """'0-3,5' -> [0, 1, 2, 3, 5]; błędne wpisy są ignorowane."""
    out: list[int] = []
    for part in (text or "").replace(" ", "").split(","):
        if not part:
            continue
        try:
            if "-" in part:
                a, b = part.split("-", 1)
                out.extend(range(int(a), int(b) + 1))
            else:
                out.append(int(part))
        except ValueError:
            continue
    max_cpu = os.cpu_count() or 64
    return sorted({c for c in out if 0 <= c < max_cpu})


def set_cpu_affinity(pid: int, cpus: list[int]) -> str:
    if not cpus:
        return ""
    try:
        psutil.Process(pid).cpu_affinity(cpus)
        return f"Powinowactwo CPU dla PID {pid}: rdzenie {cpus}."
    except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError) as exc:
        return f"Powinowactwo CPU: nie udało się ustawić ({exc})."


def suspend_processes(infos: list[ProcessInfo],
                      log: Callable[[str], None] = print) -> list[ProcessInfo]:
    """Zamraża (wstrzymuje) procesy — odwracalne, bez utraty danych."""
    done: list[ProcessInfo] = []
    for info in infos:
        try:
            proc = psutil.Process(info.pid)
            if abs((proc.create_time() or 0) - (info.create_time or 0)) > 1.0:
                continue
            fresh = ProcessInfo(pid=proc.pid, name=proc.name(),
                                exe=proc.exe() or "", create_time=info.create_time)
            if fresh.name.lower() in HARD_PROTECTED_NAMES or is_system_path(fresh.exe):
                continue
            proc.suspend()
            done.append(info)
            log(f"Zamrożono: {info.name} (PID {info.pid})")
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            log(f"Nie udało się zamrozić {info.name}: {exc}")
    return done


_SUSPENDED_STATUSES = {psutil.STATUS_STOPPED,
                       getattr(psutil, "STATUS_SUSPENDED", "suspended")}


def is_suspended(proc: "psutil.Process") -> bool:
    try:
        return proc.status() in _SUSPENDED_STATUSES
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def resume_processes(pids: Iterable[int],
                     log: Callable[[str], None] = print) -> int:
    count = 0
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            if is_suspended(proc):
                proc.resume()
                count += 1
                log(f"Odmrożono proces PID {pid}.")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return count


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums) if nums else (0,)


def is_newer_version(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def check_for_update(current_version: str, timeout: int = 8) -> Optional[dict]:
    """Sprawdza najnowszy Release na GitHubie. None = brak danych/błąd sieci."""
    import urllib.request
    url = "https://api.github.com/repos/rejson59/FocusIt/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FocusIt"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        return {"latest": tag,
                "url": data.get("html_url", ""),
                "is_newer": is_newer_version(tag, current_version)}
    except Exception:
        return None


def recover_previous_session(store: "FocusStore",
                             log: Callable[[str], None] = print) -> list[str]:
    """
    Po awarii/zabiciu FocusIt: odmraża zamrożone procesy, przywraca plan
    zasilania i (opcjonalnie) ponownie otwiera zamknięte aplikacje.
    """
    messages: list[str] = []
    state = store.load_session_state()
    if not state:
        return messages
    suspended = state.get("suspended_pids", [])
    if suspended:
        n = resume_processes(suspended, log=log)
        messages.append(f"Odmrożono {n} procesów po poprzedniej sesji.")
    power_guid = state.get("power_guid")
    if power_guid:
        manager = PowerPlanManager()
        msg = manager.restore_to(power_guid)
        messages.append(msg)
        log(msg)
    if store.settings.get("restore_apps_after_session", True):
        for exe in state.get("killed_exes", []):
            if exe and Path(exe).exists():
                log(launch_app(exe))
        if state.get("killed_exes"):
            messages.append("Ponownie uruchomiono aplikacje zamknięte "
                            "w przerwanej sesji.")
    store.clear_session_state()
    return messages
