@echo off
chcp 65001 >nul
echo === FocusIt: budowanie pliku FocusIt.exe ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
<<<<<<< HEAD
python -m PyInstaller --noconfirm --onefile --windowed --name FocusIt --icon assets\focusit.ico --add-data "assets;assets" FocusIt.py
=======
python -m PyInstaller --noconfirm --onefile --windowed --name FocusIt FocusIt.py
>>>>>>> origin/arena/ae6d22e5-focusit
echo.
echo Gotowe! Program znajdziesz w: dist\FocusIt.exe
echo (mozesz tez uruchamiac bez budowania: python FocusIt.py)
pause
