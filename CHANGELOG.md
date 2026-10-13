# Historia zmian FocusIt

## v1.4.0 — test sprzętu, auto-dopasowanie, nakładki
- 🧪 **Test możliwości urządzenia**: benchmark CPU (wszystkie rdzenie), RAM, dysku i GPU; ocena klasy sprzętu (Słaby/Średni/Mocny/Top, 0–100) i konkretne rekomendacje.
- 🎨 **Automatyczne dopasowanie grafiki w grach Unreal Engine** (np. Fortnite): FocusIt zapisuje ustawienia `GameUserSettings.ini` dopasowane do klasy sprzętu — zawsze z kopią zapasową i przyciskiem przywracania.
- ✔ **Automatyczne dopasowanie FocusIt**: po teście program sam ustawia m.in. zamrażanie zamiast zabijania przy <16 GB RAM oraz usługi sesyjne przy słabym CPU.
- 🪟 **Nakładki w grze**: kilka półprzezroczystych widżetów (czas sesji, CPU/RAM/GPU, przyciski akcji) — edytowalny zestaw, suwak przezroczystości, tryb edycji z przeciąganiem i zapamiętaną pozycją, opcjonalne klikanie „przez” nakładkę (Windows), pokazywanie na żądanie lub podczas sesji.
- 🎮 **Głębokie ustawienia**: Tryb gry Windows włączany tylko na czas sesji (z przywróceniem), preferencja GPU „Wysoka wydajność” dla wybranej gry, odblokowywanie planu „Wydajność maksymalna”. Świadomie bez „magicznych” tweaków bez dowodów działania.

## v1.3.0 — wygląd i skuteczność
- 🎨 **Nowy wygląd**: gradientowy baner „Gotowy do gry?”, odświeżona paleta (grafit + fiolet + cyjan), karty statystyk z paskami obciążenia, presety jako klikalne karty z podświetleniem, podświetlane kafelki gier, wskaźnik aktywnej sesji.
- 📉 **Pomiar obciążenia procesów w tle** (CPU) przed i po starcie sesji — raport sesji pokazuje realny efekt, np. „tło: 18,4% → 2,1%”, a nie tylko zwolniony RAM.
- 🛠 **Wstrzymywanie usług Windows na czas sesji** (telemetria DiagTrack, SysMain, Windows Update, BITS — do wyboru, wymagany administrator, usługi same wracają po sesji; są też przywracane po awarii programu).
- ❤ **Wynik kondycji PC** (0–100) z konkretnymi wskazówkami w zakładce Optymalizacja.
- 🌐 Przycisk czyszczenia pamięci podręcznej DNS.

## v1.2.1
- Poprawka techniczna: testy zamrażania działają też na Windowsie (wieloplatformowy proces testowy), odmrażanie rozpoznaje windowsowy status procesu zawieszonego. (Wydanie v1.2.0 nie przeszło bramek testów na Windowsie, dlatego nie miało pliku .exe.)

## v1.2.0
- ❄ **Zamrażanie procesów** zamiast zabijania (opcja na Panelu): procesy w tle nie zjadają CPU, nic nie tracą i same wracają po sesji.
- 🛟 **Odzyskiwanie po awarii**: jeśli FocusIt zostanie zamknięty siłą w trakcie sesji, przy następnym starcie sam odmrozi procesy, przywróci plan zasilania i ponownie otworzy zamknięte aplikacje.
- ⌨ **Skrót globalny Ctrl+Alt+F** — start/stop sesji bez wychodzenia z gry.
- ⬆ **Sprawdzanie aktualizacji** — program informuje o nowej wersji z GitHub Releases.
- 👋 **Ekran powitalny** przy pierwszym uruchomieniu (instrukcja w 30 sekund).
- 💡 **Inteligentne sugestie** na Panelu: „przed grą warto zamknąć: …” na podstawie ciężkich procesów w tle.
- 🎛 **Powinowactwo CPU w profilu gry** — można przypisać grze wybrane rdzenie (np. 0-7).
- 📊 **Wykres historii sesji** (zwolniony RAM w ostatnich 15 sesjach).

## v1.1.0
- 🎮 **Biblioteka gier**: wykrywanie gier ze Steam (z okładkami), Epic Games i GOG; dodawanie gier ręcznie.
- 👤 **Profile per gra**: dla każdej gry osobne ustawienia — co zachować, co dodatkowo zamykać, tryb sesji.
- 📈 **Wykres CPU/RAM na żywo** na Panelu gry + statystyka GPU i temperatury (NVIDIA) + lista najcięższych procesów.
- 🤖 **Auto-sesja** (opcja): automatyczny start sesji po wykryciu gry z biblioteki i auto-stop po jej zamknięciu.
- 🪟 **Mini-widget sesji** — małe okienko zawsze na wierzchu z czasem sesji i przyciskiem zakończenia.
- 🚀 Strona **Optymalizacja**: czyszczenie plików Temp (>24 h) z podglądem, menedżer autostartu (odwracalny), punkt przywracania systemu, eksport/import presetów.
- 📊 Raport po sesji pokazuje zmianę liczby procesów (przed → po) i wolny RAM.
- ⚡ Własna ikona programu (też jako ikona pliku .exe).

## v1.0.1
- Pierwszy gotowy `FocusIt.exe` publikowany w zakładce Releases (budowany automatycznie przez GitHub Actions).

## v1.0.0
- Pierwsza wersja: Panel gry, presety (Gry/Nauka/Praca/Tworzenie + własne),
  tryb łagodny i tryb IZOLACJI z twardymi regułami bezpieczeństwa,
  podgląd planu, przywracanie ustawień po sesji, historia sesji, wersja CLI.
