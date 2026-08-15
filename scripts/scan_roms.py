#!/usr/bin/env python3
"""Сканирует ~/roms/nes/*.nes и пересоздаёт плейлист RetroArch."""
import json, os, hashlib

romdir = os.path.expanduser("~/roms/nes")
core = "/usr/lib/aarch64-linux-gnu/libretro/nestopia_libretro.so"
out = os.path.expanduser("~/.config/retroarch/playlists/Nintendo - Nintendo Entertainment System.lpl")

items = []
for fn in sorted(os.listdir(romdir)):
    if not fn.lower().endswith(".nes"):
        continue
    p = os.path.join(romdir, fn)
    try:
        with open(p, "rb") as f:
            crc = format(hashlib.crc32(f.read()) & 0xFFFFFFFF, "08X")
    except Exception:
        crc = "DETECT"
    items.append({
        "path": p,
        "label": os.path.splitext(fn)[0],
        "core_path": "DETECT",
        "core_name": "DETECT",
        "crc32": crc,
        "db_name": "Nintendo - Nintendo Entertainment System.lpl",
    })

pl = {
    "version": "1.4",
    "default_core_path": core,
    "default_core_name": "Nestopia",
    "label_display_mode": 0,
    "right_thumbnail_mode": 0,
    "left_thumbnail_mode": 0,
    "sort_mode": 0,
    "items": items,
}
with open(out, "w") as f:
    json.dump(pl, f, ensure_ascii=False, indent=2)
print("Плейлист обновлён: %d игр" % len(items))
