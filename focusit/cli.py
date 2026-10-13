"""Interfejs wiersza poleceń FocusIt (podgląd / diagnostyka / automatyzacja).

Przykłady:
    python FocusIt.py --cli stats
    python FocusIt.py --cli list
    python FocusIt.py --cli plan --target game.exe --mode isolation
    python FocusIt.py --cli plan --target chrome.exe --mode gentle --close spotify.exe
"""

from __future__ import annotations

import argparse
import sys

from .core import (FocusStore, compute_plan, get_system_stats,
                   list_processes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="focusit", description="FocusIt CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats", help="Statystyki CPU/RAM")
    sub.add_parser("list", help="Lista procesów użytkownika i systemowych")
    sub.add_parser("presets", help="Lista presetów")

    p_plan = sub.add_parser("plan", help="Pokaż plan zamknięcia (TYLKO podgląd, nic nie zabija)")
    p_plan.add_argument("--target", default="", help="Nazwa pliku gry/programu, np. game.exe")
    p_plan.add_argument("--target-exe", default="", help="Pełna ścieżka do pliku .exe celu")
    p_plan.add_argument("--mode", choices=["isolation", "gentle"], default="isolation")
    p_plan.add_argument("--close", nargs="*", default=[], help="Tryb gentle: co zamknąć")
    p_plan.add_argument("--keep", nargs="*", default=[], help="Dodatkowa lista Zachowaj")
    p_plan.add_argument("--all", action="store_true", help="Pokaż też zachowane procesy")

    args = parser.parse_args(argv)
    store = FocusStore()

    if args.cmd == "stats":
        s = get_system_stats()
        print(f"CPU: {s['cpu_percent']:.0f}% | RAM: {s['ram_used_gb']}/{s['ram_total_gb']} GB "
              f"({s['ram_percent']:.0f}%) | procesy: {s['process_count']}")
        return 0

    if args.cmd == "list":
        for p in list_processes():
            print(f"{p.pid:>7}  {p.memory_mb:>9.1f} MB  {p.name:<35} {p.exe}")
        return 0

    if args.cmd == "presets":
        for p in store.presets:
            print(f"{p.get('icon','')} {p['name']:<12} tryb={p.get('mode')} — {p.get('description','')}")
        return 0

    if args.cmd == "plan":
        processes = list_processes()
        keep = set(args.keep) | set(store.settings.get("keep_always", []))
        plan = compute_plan(processes, target_exe=args.target_exe,
                            target_name=args.target, mode=args.mode,
                            close_names=args.close, keep_names=keep)
        print(f"Cel: {args.target or args.target_exe or '(brak)'} | tryb: {args.mode}")
        print(plan.summary())
        print("\n--- DO ZAMKNIĘCIA ---")
        for d in plan.kill_list:
            print(f"  PID {d.proc.pid:>6}  {d.proc.memory_mb:>8.1f} MB  "
                  f"{d.proc.name:<35} ({d.reason})")
        if args.all:
            print("\n--- ZACHOWANE ---")
            for d in plan.keep_list:
                print(f"  PID {d.proc.pid:>6}  {d.proc.memory_mb:>8.1f} MB  "
                      f"{d.proc.name:<35} [{d.category}] {d.reason}")
        print("\nTo był tylko PODGLĄD — żaden proces nie został zamknięty.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
