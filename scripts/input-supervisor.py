#!/usr/bin/env python3
"""input-supervisor.py — сторож игрового ввода (Zero 3W).

Задача: игра RetroArch и драйвер m5hub не могут работать одновременно (делят шину
I2C с клавиатурой). Раньше лаунчер останавливал m5hub на всю игру и возвращал его
только при выходе — поэтому если игру СВЕРНУТЬ, на рабочем столе молчали джойстик,
скролл и клавиатура, пока игру не закроешь.

Сторож решает это: следит за окном RetroArch и переключает режим сам.

  окно RetroArch есть, но НЕ отображено  (игра свёрнута)  -> рабочий стол:
        гасим игровой мост, поднимаем m5hub
  окно отображено, ИЛИ окна ещё нет (меню выбора игры)   -> игра:
        пауза m5hub, поднимаем игровой мост

Живёт только на время сессии игры: лаунчер ставит /tmp/retrogame.lock и снимает его
при выходе — сторож сам завершается вместе с замком и уводит свой мост за собой.
"""
import os
import signal
import subprocess
import sys
import time

LOCK = "/tmp/retrogame.lock"
BRIDGE = "/home/orangepi/.openclaw/workspace/game_input.py"
BRIDGE_LOG = "/tmp/game_bridge.log"
ENV = dict(os.environ)
ENV.setdefault("DISPLAY", ":0")
ENV.setdefault("XAUTHORITY", "/home/orangepi/.Xauthority")

bridge_proc = None
stop = False


def log(msg):
    print("[supervisor] " + msg, flush=True)


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return ""


def retroarch_unmapped():
    """True, если окно RetroArch существует, но не отображается (игра свёрнута)."""
    ids = set()
    for args in (["xdotool", "search", "--class", "retroarch"],
                 ["xdotool", "search", "--name", "RetroArch"]):
        for w in run(args).split():
            ids.add(w)
    if not ids:
        return False            # окна нет — это меню выбора игры, мост нужен
    for w in ids:
        info = run(["xwininfo", "-id", w])
        if "IsViewable" in info:
            return False        # игра на экране — нужен игровой режим
    return True                 # окно есть, но скрыто — игра свёрнута


def m5hub_active():
    return run(["systemctl", "is-active", "m5hub"]).strip() == "active"


def bridge_alive():
    return bridge_proc is not None and bridge_proc.poll() is None


def start_bridge():
    global bridge_proc
    if bridge_alive():
        return
    try:
        logf = open(BRIDGE_LOG, "a")
        bridge_proc = subprocess.Popen(["python3", BRIDGE], env=ENV,
                                       stdout=logf, stderr=logf,
                                       stdin=subprocess.DEVNULL)
        log("🎮 игровой мост запущен (pid %d)" % bridge_proc.pid)
    except Exception as e:
        log("не смог запустить мост: %s" % e)


def stop_bridge():
    global bridge_proc
    if bridge_proc is not None and bridge_proc.poll() is None:
        try:
            bridge_proc.terminate()
            bridge_proc.wait(timeout=5)
        except Exception:
            try:
                bridge_proc.kill()
            except Exception:
                pass
        log("мост остановлен")
    bridge_proc = None


def wait_m5hub(want, secs=15.0):
    """Ждём, пока служба реально перейдёт в нужное состояние.

    Без этого ожидания выходило так: мост стартовал и калибровал джойстик, пока
    драйвер ещё держал шину I2C — центр уезжал, и персонаж бежал сам по себе.
    """
    t0 = time.time()
    while time.time() - t0 < secs:
        if m5hub_active() == want:
            return True
        time.sleep(0.5)
    return False


def m5hub_start():
    run(["sudo", "-n", "systemctl", "start", "m5hub"])
    if wait_m5hub(True):
        log("🖥️  m5hub поднят — ввод на рабочем столе")
    else:
        log("⚠️ m5hub не поднялся за 15 с")


def m5hub_stop():
    run(["sudo", "-n", "systemctl", "stop", "m5hub"])
    if wait_m5hub(False):
        time.sleep(0.5)          # шина успокаивается после чужого опроса
        log("🛑 m5hub остановлен — шина отдана игре")
    else:
        log("⚠️ m5hub не остановился за 15 с — мост поднимать небезопасно")


def on_term(sig, frm):
    global stop
    stop = True


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    log("старт, жду игру (замок %s)" % LOCK)
    state = None
    while not stop:
        if not os.path.exists(LOCK):
            log("сессия игры завершена — выхожу")
            break
        hidden = retroarch_unmapped()
        want = "desktop" if hidden else "game"
        if want != state:
            state = want
            if hidden:
                log("игра свёрнута → возвращаю ввод на рабочий стол")
                stop_bridge()
                m5hub_start()
            else:
                log("игра на экране → отдаю ввод игре")
                m5hub_stop()
                start_bridge()
        # если игра уже на экране, а мост почему-то умер — поднять
        if state == "game" and not bridge_alive():
            log("мост не отвечает — перезапускаю")
            start_bridge()
        time.sleep(2)
    stop_bridge()
    time.sleep(0.5)              # даём мосту отпустить шину I2C
    log("завершён")
