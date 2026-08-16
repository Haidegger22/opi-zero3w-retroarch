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
