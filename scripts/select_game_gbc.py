#!/usr/bin/env python3
"""Выбор GBC/GBA-игры через zenity и запуск RetroArch с mGBA."""
import os, subprocess, sys

ROMDIR = os.path.expanduser("~/roms/gbc")
CORE = os.path.expanduser("~/.config/retroarch/cores/mgba_libretro.so")
CFG = os.path.expanduser("~/.config/retroarch/gbc.cfg")

exts = (".gb", ".gbc", ".gba")
roms = sorted(
    os.path.join(ROMDIR, f) for f in os.listdir(ROMDIR)
    if f.lower().endswith(exts)
)
if not roms:
    print("Нет GBC/GBA-игр в", ROMDIR, file=sys.stderr)
    sys.exit(1)

labels = [os.path.basename(p) for p in roms]
args = ["zenity", "--list", "--title=Выбор GBC игры",
        "--text=Выбери игру (джойстик/стрелки + Enter, Esc — отмена)",
        "--column=Игра", "--column=Путь", "--hide-column=2",
        "--print-column=2", "--height=320", "--width=480"]
for lbl, p in zip(labels, roms):
    args += [lbl, p]

r = subprocess.run(args, capture_output=True, text=True, env={**os.environ, "DISPLAY": ":0"})
if r.returncode != 0:
    sys.exit(0)
selected = r.stdout.strip()
if not selected:
    sys.exit(0)

print("[gbc] Выбрана игра:", os.path.basename(selected))
cmd = ["retroarch", "-L", CORE, "--appendconfig", CFG, selected]
subprocess.run(cmd, env={**os.environ, "DISPLAY": ":0", "SDL_INPUT_LINUXEV": "0"})
