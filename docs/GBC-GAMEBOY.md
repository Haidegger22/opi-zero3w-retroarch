# 🎮 Game Boy (GBC/GBA) на RetroArch — Orange Pi Zero 3W

Полная инструкция по эмуляции Game Boy / Game Boy Color / Game Boy Advance на Orange Pi Zero 3W (Allwinner A733, Debian 11 bullseye) через RetroArch + ядро **mGBA**.

Включает **реальные команды** из сессии отладки 16.08.2026 — с описанием всех граблей, на которые мы наступили, и их решений.

---

## 📋 Итоговая архитектура

| Элемент | Значение |
|---------|----------|
| RetroArch | 1.14.0 (bullseye-backports) |
| Core | `mgba_libretro.so` (скачан с buildbot.libretro.com) |
| Видео-драйвер | **`xvideo`** ⚠️ (не `gl`, не `sdl2` — см. раздел «Проблемы») |
| ROM'ы | `~/roms/gbc/` (`.gb`, `.gbc`, `.gba`) |
| Лаунчер | `retrogame-gbc.sh` + `select_game_gbc.py` (выбор через zenity) |
| Ярлык | `~/Desktop/gbc.desktop` («🎮 Game Boy (GBC/GBA)») |
| Управление | Джойстик V2 → D-pad, GPIO A/B → кнопки, CardKB → Start/Select/Esc |

---

## 📦 Шаг 1. Скачиваем core mGBA

В apt Debian 11 core'а mGBA для libretro **нет** (`apt-cache policy libretro-mgba` пуст), поэтому качаем с buildbot.libretro.com.

> ⚠️ **Важно:** на самом Zero 3W прямая загрузка с buildbot часто обрывается по таймауту (код 28, приходит HTML-файл 17 КБ вместо архива). Поэтому качаем на Pi 5 (или любом стабильном ПК) и перекидываем по scp.

```bash
# На Pi 5 (или ПК):
cd /tmp
curl -sL -o mgba.zip --max-time 90 \
  "https://buildbot.libretro.com/nightly/linux/aarch64/latest/mgba_libretro.so.zip"
unzip -o mgba.zip
ls -la mgba_libretro.so        # ~3.2 МБ

# Перекидываем на Zero 3W:
sshpass -p '<ПАРОЛЬ>' scp mgba_libretro.so orangepi@<IP_ZERO>:/tmp/

# На Zero 3W — ставим на место:
sshpass -p '<ПАРОЛЬ>' ssh orangepi@<IP_ZERO> '
  mkdir -p ~/.config/retroarch/cores
  cp /tmp/mgba_libretro.so ~/.config/retroarch/cores/
  ldd ~/.config/retroarch/cores/mgba_libretro.so | grep "not found" \
    || echo "зависимости в порядке"
'
```

---

## 📁 Шаг 2. Папка для ROM'ов

```bash
sshpass -p '<ПАРОЛЬ>' ssh orangepi@<IP_ZERO> '
  mkdir -p ~/roms/gbc
  # ROM кладём сюда, например:
  # mv "Shantae (USA).gbc" ~/roms/gbc/
'
```

---

## 🕹️ Шаг 3. Лаунчер и выбор игры

### `select_game_gbc.py` — выбор игры через zenity

```bash
sshpass -p '<ПАРОЛЬ>' ssh orangepi@<IP_ZERO> 'cat > ~/.openclaw/workspace/select_game_gbc.py' << 'PYEOF'
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
PYEOF
```

### `retrogame-gbc.sh` — обёртка (пауза m5hub → мост → выбор игры → возврат)

```bash
sshpass -p '<ПАРОЛЬ>' ssh orangepi@<IP_ZERO> 'cat > ~/.openclaw/workspace/retrogame-gbc.sh' << 'EOF'
#!/bin/bash
# 🕹️ RetroArch (GBC/GBA) — mGBA + выбор игры
LOCK=/tmp/retrogame-gbc.lock
if [ -f "$LOCK" ]; then
    PID=$(cat "$LOCK" 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "[gbc] уже запущено (PID $PID) — выхожу"
        exit 0
    fi
    rm -f "$LOCK"
fi
echo $$ > "$LOCK"

cd /home/orangepi
BRIDGE=""

cleanup() {
  echo "[gbc] Завершение..."
  [ -n "$BRIDGE" ] && kill "$BRIDGE" 2>/dev/null || true
  sleep 0.5
  rm -f "$LOCK"
  echo "[gbc] ✅ Возвращаю m5hub..."
  sudo systemctl start m5hub 2>/dev/null || true
}
trap cleanup EXIT

echo "[gbc] 🛑 Пауза m5hub..."
sudo systemctl stop m5hub 2>/dev/null || true
sleep 1

echo "[gbc] 🎮 Запускаю игровой мост..."
DISPLAY=:0 python3 /home/orangepi/.openclaw/workspace/game_input.py &
BRIDGE=$!

sleep 1
echo "[gbc] 🕹️ Выбор GBC-игры..."
DISPLAY=:0 python3 /home/orangepi/.openclaw/workspace/select_game_gbc.py
EOF
chmod +x ~/.openclaw/workspace/retrogame-gbc.sh ~/.openclaw/workspace/select_game_gbc.py
```

> ℹ️ Мост `game_input.py` (см. `scripts/game_input.py` в этом репозитории) эмулирует джойстик → стрелки, GPIO A/B → клавиши, CardKB → Start/Select/Esc. Во время игры m5hub останавливается, чтобы не было конфликта за I2C-шину, и возвращается после выхода.

---

## 🖥️ Шаг 4. Конфиг видео и кнопок

> ⚠️ **Это самый важный файл.** Видео-драйвер должен быть `xvideo` — подробности в разделе «Проблемы».

```bash
sshpass -p '<ПАРОЛЬ>' ssh orangepi@<IP_ZERO> 'cat > ~/.config/retroarch/gbc.cfg' << 'EOF'
video_driver = "xvideo"
video_shader_enable = "false"
audio_driver = "pulse"
input_player1_a = "num0"
input_player1_b = "Backspace"
input_player1_start = "enter"
input_player1_select = "space"
EOF
```

Раскладка кнопок (для Shantae и большинства GBC-платформеров):
- **A (GPIO 96)** → `num0` → атака/действие
- **B (GPIO 131)** → `Backspace` → прыжок
- CardKB: Enter = Start, Space = Select

> 🔁 Если кнопки перепутаны местами — поменяй `num0` и `Backspace` местами в `gbc.cfg`.

---

## 🏠 Шаг 5. Ярлык на рабочем столе (GNOME)

```bash
sshpass -p '<ПАРОЛЬ>' ssh orangepi@<IP_ZERO> 'cat > ~/Desktop/gbc.desktop' << 'EOF'
[Desktop Entry]
Type=Application
Name=🎮 Game Boy (GBC/GBA)
Comment=Shantae и другие GBC/GBA-игры (mGBA)
Exec=bash /home/orangepi/.openclaw/workspace/retrogame-gbc.sh
Icon=/usr/share/pixmaps/retroarch.svg
Terminal=false
Categories=Game;
EOF
chmod +x ~/Desktop/gbc.desktop
```

---

## 🐛 Проблемы, на которые мы наступили (и как их чинили)

### Проблема 1. Ярлык на рабочем столе не запускается (GNOME)

**Симптом:** клик по ярлыку — ничего не происходит. При этом сам скрипт из терминала работает.

**Причина:** GNOME (в отличие от Windows) не запускает `.desktop`-файлы с рабочего стола, пока файлу не выставлен флаг доверия `metadata::trusted`. Без него клик игнорируется (расширение рабочего стола `desktop-icons@csoriano` кэширует статус при загрузке).

**Решение:**
```bash
export DISPLAY=:0
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"

# Помечаем ярлык как доверенный (эквивалент правый клик → «Разрешить запуск»)
gio set ~/Desktop/gbc.desktop metadata::trusted true

# Перезапускаем расширение рабочего стола, чтобы оно перечитало флаг
gnome-extensions disable desktop-icons@csoriano
sleep 2
gnome-extensions enable desktop-icons@csoriano
```

**Проверка:**
```bash
gio info ~/Desktop/gbc.desktop | grep trusted   # metadata::trusted: true
```

> 💡 Пользовательский путь (без команд): правый клик по ярлыку → «Разрешить запуск».
> Альтернатива: продублировать ярлык в `~/.local/share/applications/` — оттуда GNOME запускает без флага доверия (доступно через Activities → поиск).

---

### Проблема 2. Игра падает с segfault при выборе

**Симптом:** окно выбора игры открывается, выбираешь Shantae — RetroArch падает с `Ошибка сегментирования` (exit 139).

**Лог:**
```
[INFO] [EGL]: EGL version: 1.5
[INFO] [GL]: Found GL context: "egl_x".
[INFO] [GL]: Vendor: Imagination Technologies, Renderer: PowerVR B-Series BXM-4-64.
[INFO] [GLSL]: Linking GLSL program.
... падение (segfault)
```

**Причина:** видео-драйвер `gl` по умолчанию компилирует GLSL-шейдеры, а GPU **PowerVR BXM-4-64** на A733 падает на этом (та же болезнь, что была у Cave Story/NXEngine).

**Решение:** переключиться на рендер, не использующий OpenGL-шейдеры.

**Проверка доступных драйверов:**
```bash
retroarch --features | grep -iE "Video"
# OpenGL - Video driver: yes
# OpenGLES - Video driver: yes
# XVideo - Video driver: yes
# SDL2 - SDL2 input/audio/video drivers: yes
```

---

### Проблема 3. Чёрный экран при выборе «sdl2»

**Симптом:** после перехода на `video_driver = "sdl2"` игра больше не падает (процесс жив), но экран полностью чёрный.

**Лог:**
```
[ERROR] [SDL2]: Failed to initialize renderer: Couldn't find matching render driver
[ERROR] [SDL2]: Failed to create main texture: Invalid renderer
```

**Причина:** SDL2-рендерер на этой системе не создаётся вообще (`Couldn't find matching render driver`) — видимо, в сборке SDL2 нет подходящего бэкенда для PowerVR. Процесс живёт, но рисовать нечем.

**Решение:** использовать **`xvideo`** — аппаратный оверлей X11 (XvPort), которому не нужны ни OpenGL, ни SDL2-рендерер.

**Проверка, что драйвер реально рисует** (скриншот через ffmpeg):
```bash
export DISPLAY=:0
retroarch -L ~/.config/retroarch/cores/mgba_libretro.so \
  --appendconfig ~/.config/retroarch/gbc.cfg \
  "~/roms/gbc/Shantae (USA).gbc" &
sleep 6
~/bin/ffmpeg -y -f x11grab -video_size 1024x600 -i :0 -frames:v 1 /tmp/shot.png
ls -la /tmp/shot.png
# ✅ картинка: файл ~190-200 КБ (титульный экран Shantae)
# ❌ чёрный экран: файл ~1-15 КБ
```

**Лог при успехе:**
```
[INFO] [XVideo]: Found suitable XvPort #80
[INFO] [Video]: Found display server: "x11".
```

---

### Сводка по видео-драйверам (Zero 3W + PowerVR)

| Драйвер | Результат |
|---------|-----------|
| `gl` (по умолчанию) | ❌ segfault на GLSL-шейдерах |
| `sdl2` | ❌ чёрный экран (рендерер не создаётся) |
| `sdl2` + `SDL_RENDER_DRIVER=software` | ❌ тоже чёрный экран |
| **`xvideo`** | ✅ **работает** (XvPort #80) |

> 🏆 **Вывод: на Zero 3W с PowerVR для RetroArch правильный видео-драйвер — `xvideo`.**

---

## ▶️ Запуск

```bash
# Через ярлык рабочего стола
# или из терминала:
bash ~/.openclaw/workspace/retrogame-gbc.sh
```

Последовательность при запуске:
1. m5hub ставится на паузу (освобождает I2C-шину)
2. Стартует игровой мост `game_input.py`
3. Открывается окно выбора игры (zenity) — список из `~/roms/gbc/`
4. После выбора запускается RetroArch + mGBA с конфигом `gbc.cfg`
5. При выходе из игры мост убивается, m5hub возвращается

---

## 🎮 Проверенные игры

| Игра | Платформа | Статус |
|------|-----------|--------|
| Shantae (USA) | GBC | ✅ работает (титульный экран, геймплей) |

---

## 📁 Файлы в этом репозитории

- `config/gbc.cfg` — видео/кнопки (xvideo!)
- `config/gbc.desktop` — ярлык рабочего стола
- `scripts/select_game_gbc.py` — выбор игры через zenity
- `scripts/retrogame-gbc.sh` — лаунчер
