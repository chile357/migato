# 🐱 MiGato

Mascota de escritorio con cerebro: hambre, aburrimiento, afecto, estrés,
memoria persistente y utility AI. Hecho con PySide6.

## ✨ Features
- 9 estados animados (idle, walk, run, sleep, pounce, clean, stretch, front, meow)
- Stats internos: energía, hambre, aburrimiento, afecto, estrés
- Detección de actividad del usuario (mouse idle)
- System tray: alimentar, acariciar, mostrar/ocultar
- Sigue el cursor, hace pounce, huye si lo estresas
- Persistencia en `save.json` (local, no se sube al repo)

## 📦 Instalación

git clone https://github.com/tu-usuario/migato.git
cd migato
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

## ▶️ Ejecutar

python main.py

## 🛠️ Build (Windows)

pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --add-data "assets;assets" --name MiGato pet.py

## 📂 Estructura
- `main.py` — punto de entrada
- `pet.py` — clase Pet (cerebro + UI)
- `bubble.py` — burbuja de diálogo
- `senses.py` — eventos sensoriales
- `reminders.py` — recordatorios
- `assets/cat_sheet.png` — sprite sheet 6x4

## 📜 Licencia
MIT