#!/usr/bin/env python3
"""Выбор игры через zenity и запуск RetroArch с выбранным ROM."""
import os, subprocess, sys

ROMDIR = os.path.expanduser("~/roms/nes")
CORE = "/usr/lib/aarch64-linux-gnu/libretro/nestopia_libretro.so"

roms = sorted(
    os.path.join(ROMDIR, f) for f in os.listdir(ROMDIR) if f.lower().endswith(".nes")
)
if not roms:
    print("Нет .nes файлов в", ROMDIR, file=sys.stderr)
    sys.exit(1)

labels = [os.path.basename(p)[:-4] for p in roms]

# zenity --list: колонка «Игра» + скрытая колонка «Путь»
args = ["zenity", "--list", "--title=Выбор игры",
        "--text=Выбери игру (джойстик/стрелки + Enter, Esc — отмена)",
        "--column=Игра", "--column=Путь", "--hide-column=2",
        "--print-column=2", "--height=320", "--width=480"]
for lbl, p in zip(labels, roms):
    args += [lbl, p]

r = subprocess.run(args, capture_output=True, text=True, env={**os.environ, "DISPLAY": ":0"})
if r.returncode != 0:
    # отмена
    sys.exit(0)

selected = r.stdout.strip()
if not selected:
    sys.exit(0)

print("[retro] Выбрана игра:", os.path.basename(selected))
subprocess.run(["retroarch", "-L", CORE, selected],
               env={**os.environ, "DISPLAY": ":0", "SDL_INPUT_LINUXEV": "0"})
