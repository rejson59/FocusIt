# Historia zmian FocusIt

## v1.6.0 — prawdziwe 100% urządzenia, bez fioletu
- 💚 **Usunięto fiolet całkowicie** — jedynym motywem jest Neon Honeycomb (matowa czerń + neonowa zieleń).
- 🧪 **Rozbudowane testy wydajności**: CPU 1-rdzeń i wielordzeń ze skalowaniem, test obciążenia ciągłego wykrywający **throttling**, latencja RAM, dysk sekwencyjny + **losowy 4K IOPS**, historia wyników i wnioski (wąskie gardła: jednowątkowość, chłodzenie, XMP, HDD).
- 🖥 **Inwentaryzacja sprzętu**: model CPU, moduły RAM z taktowaniem, GPU, dyski i wersja systemu w raporcie testu.
- ⚙ **Pełny plan sesji Windows**: plan „Wydajność maksymalna” + procesor 100% bez parkowania rdzeni, PCIe bez oszczędzania, USB/dysk bez usypiania (tylko na czas sesji).
- 🎬 **Game DVR OFF na sesję** (nagrywanie w tle zjada FPS), **timer 1 ms na sesję**, priorytet CPU+IO gry.
- 📋 **Raport optymalizacji Windows**: Tryb gry, Game DVR, HAGS (z przełącznikiem, restart), VBS (tylko informacja — bezpieczeństwa nie ruszamy), TRIM, odświeżanie monitora, plan zasilania.
- 🖥 **Wyłączanie optymalizacji pełnoekranowych** dla wybranej gry (prawdziwy exclusive fullscreen), odwracalne.

## v1.5.0 — Neon Honeycomb Game Bar
- ⬢ **Całkowicie nowy motyw „Neon Honeycomb”**: matowa czerń, neonowa zieleń i plastry miodu z rozproszoną poświatą (menu boczne, baner „Gotowy do gry?”, ramki, wykresy, nakładki).
- 🎴 Karty statystyk i presetów dopasowane do motywu (neonowe paski obciążenia, podświetlenia, status SYSTEM GOTOWY / SESJA AKTYWNA).
- 🪟 Nakładki w grze w tym samym klimacie: ciemne, półprzezroczyste, z neonową ramką.
- ⚡ Nowa ikona programu: neonowy błysk na plastrach miodu.
- 🎨 Przełącznik motywu w Ustawieniach: **Neon Honeycomb** albo klasyczny grafitowo-fioletowy (wymaga restartu programu).
- 🖼 Wizualizacja motywu w README (docs/neon-gamebar-preview.png).

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
