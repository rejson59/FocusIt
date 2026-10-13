#!/usr/bin/env python3
"""FocusIt — punkt startowy.

    python FocusIt.py              -> okno programu
    python FocusIt.py --cli plan --target game.exe   -> podgląd planu w terminalu
"""

import sys

if __name__ == "__main__":
    if "--cli" in sys.argv:
        from focusit.cli import main
        sys.exit(main([a for a in sys.argv[1:] if a != "--cli"]))
    try:
        from focusit.gui import run_gui
        run_gui()
    except ImportError as exc:
        print("Nie udało się uruchomić okna programu:", exc)
        print("Sprawdź, czy masz zainstalowane zależności:  pip install -r requirements.txt")
        print("Wersja tekstowa:  python FocusIt.py --cli plan --target game.exe")
        sys.exit(1)
