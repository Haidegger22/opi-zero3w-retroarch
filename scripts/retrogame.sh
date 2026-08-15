#!/bin/bash
# 🕹️ RetroArch (NES) — единый игровой демон + выбор игры
# m5hub НЕ меняем: только пауза на время игры и возврат после.
# Джойстик V2 = D-pad, GPIO A/B = прыжок/удар, CardKB = Start/Select/Esc.

# ── Защита от повторного запуска ──
LOCK=/tmp/retrogame.lock
if [ -f "$LOCK" ]; then
    PID=$(cat "$LOCK" 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "[retro] уже запущено (PID $PID) — выхожу"
        exit 0
    fi
    rm -f "$LOCK"
fi
echo $$ > "$LOCK"

cd /home/orangepi

BRIDGE=""

cleanup() {
  echo "[retro] Завершение..."
  [ -n "$BRIDGE" ] && kill "$BRIDGE" 2>/dev/null || true
  sleep 0.5
  rm -f "$LOCK"
  echo "[retro] ✅ Возвращаю m5hub..."
  sudo systemctl start m5hub 2>/dev/null || true
}
trap cleanup EXIT

echo "[retro] 🛑 Пауза m5hub (освобождаю I2C)..."
sudo systemctl stop m5hub 2>/dev/null || true
sleep 1

echo "[retro] 🎮 Запускаю игровой мост..."
DISPLAY=:0 python3 /home/orangepi/.openclaw/workspace/game_input.py &
BRIDGE=$!

sleep 1
echo "[retro] 🕹️ Выбор игры..."
DISPLAY=:0 python3 /home/orangepi/.openclaw/workspace/select_game.py
