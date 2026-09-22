#!/usr/bin/env python3
"""
game_input.py — единый игровой мост (RetroArch + Mario).
Работает ТОЛЬКО на время игры (m5hub остановлен), чтобы не было конфликта на I2C-шине.
- Джойстик V2 (I2C/PaHub канал 0, адрес 0x63) → стрелки (D-pad)
- GPIO 96 → A (прыжок, клавиша "0");  GPIO 131 → B (бег, Backspace)
- CardKB (I2C/PaHub канал 2, 0x5F) → Enter=Start, Space=Select, Esc=выход
Эмуляция через XTest (X11). Без зависимостей от m5hub.
"""
import os, fcntl, time, ctypes, collections, statistics, subprocess
import gpiod
from Xlib import display, X
from Xlib.ext import xtest

I2C_BUS = 0
I2C_RDWR = 0x0707
I2C_M_RD = 1


class m(ctypes.Structure):
    _fields_ = [('addr', ctypes.c_uint16), ('flags', ctypes.c_uint16),
                ('len', ctypes.c_uint16), ('buf', ctypes.POINTER(ctypes.c_uint8))]


class d(ctypes.Structure):
    _fields_ = [('msgs', ctypes.POINTER(m)), ('nmsgs', ctypes.c_uint32)]


_g = []


def i2c_wr(fd, ad, da):
    b = (ctypes.c_uint8 * len(da))(*da)
    mg = m(ad, 0, len(da), b)
    wd = d(ctypes.pointer(mg), 1)
    _g.extend([b, mg, wd])
    fcntl.ioctl(fd, I2C_RDWR, wd)
    _g.clear()
    time.sleep(0.002)


def i2c_rd(fd, ad, re, n):
    wb = (ctypes.c_uint8 * 1)(re)
    rb = (ctypes.c_uint8 * n)()
    m0 = m(ad, 0, 1, wb)
    m1 = m(ad, I2C_M_RD, n, rb)
    ms = (m * 2)(m0, m1)
    wd = d(ms, 2)
    _g.extend([wb, rb, m0, m1, ms, wd])
    fcntl.ioctl(fd, I2C_RDWR, wd)
    _g.clear()
    return bytes(rb)


def i2c_rr(fd, ad, n):
    rb = (ctypes.c_uint8 * n)()
    mg = m(ad, I2C_M_RD, n, rb)
    wd = d(ctypes.pointer(mg), 1)
    _g.extend([rb, mg, wd])
    fcntl.ioctl(fd, I2C_RDWR, wd)
    _g.clear()
    return bytes(rb)


class GameInput:
    def __init__(self):
        self.fd = os.open('/dev/i2c-%d' % I2C_BUS, os.O_RDWR)
        _g.append(self.fd)
        self.disp = display.Display(':0')
        self._rst()
        self.cx = self.cy = 32768
        self._cal()
        self.kc = {}
        self.state = {}
        self._kl = 0
        self._kb = {}                 # состояние клавиш CardKB (в новом режиме)
        self._bits_prev = 0           # маска зажатых клавиш в прошлом опросе
        self._mods_prev = 0           # модификаторы (Shift/Sym/Fn) в прошлом опросе
        self._fn = False              # слой Fn включён и ждёт клавишу
        self._swallow_enter = False   # не отдавать Start, пока зажата комбинация
        self._kb_mode(1)              # включаем в клавиатуре режим сканирования нажатий
        self._jhist = collections.deque(maxlen=4)
        # GPIO кнопки (pull-up, 0 = нажата) — libgpiod v2 API
        from gpiod.line import Direction, Bias, Value
        self._gv = Value
        self._req = gpiod.request_lines(
            '/dev/gpiochip0', consumer='game-input',
            config={96: gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP),
                    131: gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP)})
        self._gpio_state = {96: 1, 131: 1}

    # ── PaHub ──
    def _rst(self):
        try:
            i2c_wr(self.fd, 0x70, [0x00])
            time.sleep(0.01)
        except Exception:
            pass

    def sel(self, c):
        try:
            i2c_wr(self.fd, 0x70, [0x00])
            time.sleep(0.001)
        except Exception:
            pass
        i2c_wr(self.fd, 0x70, [1 << c])
        time.sleep(0.005)

    def _kb_mode(self, m):
        """Режим клавиатуры: 0 — обычный, 1 — сканирование удержанных клавиш."""
        try:
            self.sel(2)
            i2c_wr(self.fd, 0x5F, [0x20, m])
        except Exception:
            pass

    def rd(self, c, a, re, n):
        self.sel(c)
        # Первый ответ после переключения канала PaHub бывает от ПРЕДЫДУЩЕГО
        # канала (например, данные джойстика приходят вместо маски клавиатуры,
        # и в игру уходит ложная стрелка). Один холостой замер это снимает.
        i2c_rd(self.fd, a, re, n)
        return i2c_rd(self.fd, a, re, n)

    def rr(self, c, a, n):
        self.sel(c)
        return i2c_rr(self.fd, a, n)

    def _cal(self):
        xs, ys = [], []
        for _ in range(50):
            try:
                dd = self.rd(0, 0x63, 0x00, 4)
                xs.append(dd[0] | (dd[1] << 8))
                ys.append(dd[2] | (dd[3] << 8))
            except Exception:
                pass
            time.sleep(0.01)
        if xs:
            # медиана, а не среднее: единичный сбойный замер не уводит центр
            self.cx = int(statistics.median(xs))
            self.cy = int(statistics.median(ys))
            print('[game] center X=%d Y=%d' % (self.cx, self.cy))

    # ── XTest ──
    def _keycode(self, keysym):
        if keysym not in self.kc:
            kc = self.disp.keysym_to_keycode(keysym)
            if not kc:
                kc = self.disp.keysym_to_keycode(0x20)
            self.kc[keysym] = kc
        return self.kc[keysym]

    def key(self, keysym, press):
        was = self.state.get(keysym, False)
        if press == was:
            return
        kc = self._keycode(keysym)
        xtest.fake_input(self.disp, X.KeyPress if press else X.KeyRelease, kc)
        self.disp.flush()
        self.state[keysym] = press

    def release_all(self):
        for ks in list(self.state):
            if self.state[ks]:
                self.key(ks, False)

    # ── Джойстик → стрелки ──
    def _joy(self):
        try:
            dd = self.rd(0, 0x63, 0x00, 4)
        except Exception:
            return
        x = dd[0] | (dd[1] << 8)
        y = dd[2] | (dd[3] << 8)
        dx, dy = x - self.cx, y - self.cy

        if abs(dx) < 6000 and abs(dy) < 6000:
            self._jhist.clear()
            sdx = sdy = 0
        else:
            self._jhist.append((dx, dy))
            if len(self._jhist) > 5:
                del self._jhist[0]
            # Пока накопилось меньше трёх замеров — не двигаем: одиночный
            # сбойный замер на шине иначе сразу превращается в стрелку
            # (персонаж «бежит назад» сам по себе).
            if len(self._jhist) < 3:
                return
            sdx = statistics.median([p[0] for p in self._jhist])
            sdy = statistics.median([p[1] for p in self._jhist])

        DEAD = 5000

        # Snap к доминирующей оси: диагональный наклон даёт только одну стрелку.
        # Если одна ось в 2+ раза сильнее другой — слабую зануляем.
        # Убирает ложные диагонали и «залипание» между направлениями (танчики).
        if abs(sdx) > abs(sdy) * 2:
            sdy = 0
        elif abs(sdy) > abs(sdx) * 2:
            sdx = 0

        LEFT, RIGHT, UP, DOWN = 0xFF51, 0xFF53, 0xFF52, 0xFF54
        self.key(LEFT, (sdx < -DEAD) or self._kb.get(LEFT, False))
        self.key(RIGHT, (sdx > DEAD) or self._kb.get(RIGHT, False))
        self.key(UP, (sdy < -DEAD) or self._kb.get(UP, False))
        self.key(DOWN, (sdy > DEAD) or self._kb.get(DOWN, False))
        for ks in (0xFF1B, 0xFF0D, 0x0020):
            self.key(ks, self._kb.get(ks, False))

    # ── CardKB → Start/Select/Esc + стрелки (с удержанием) ──
    # Индексы по таблице прошивки M5Stack: 0=Esc, 24=влево, 25=вверх,
    # 35=Enter, 36=вниз, 37=вправо, 47=пробел.
    def _cardkb(self):
        try:
            dd = self.rd(2, 0x5F, 0x10, 7)     # 7 байт: 48 клавиш + модификаторы
        except Exception:
            return
        if not dd or len(dd) < 7:
            return
        bits = int.from_bytes(dd[:6], "little")   # бит i = клавиша с индексом i зажата
        mods = dd[6]                              # 0x01 Shift, 0x02 Sym, 0x04 Fn
        new = bits & ~self._bits_prev             # клавиши, нажатые именно в этом опросе
        self._bits_prev = bits
        def held(i):
            return bool((bits >> i) & 1)
        def newp(i):
            return bool((new >> i) & 1)

        # ── Fn-комбинации: те же, что работают на рабочем столе ──
        if (mods & 0x04) and not (self._mods_prev & 0x04):
            self._fn = True                  # Fn нажат: слой включён и ждёт клавишу
        self._mods_prev = mods
        fn_used = False
        if self._fn:
            if newp(11):                     # Fn+Backspace — погасить экран
                self._run('xset', 'dpms', 'force', 'off')
                print('[game] 🌙 Экран погашен (Fn+Backspace)')
                fn_used = True
            elif newp(35):                   # Fn+Enter — свернуть игру, показать рабочий стол
                self._run('xdotool', 'key', '--clearmodifiers', 'ctrl+alt+d')
                print('[game] 🗂️ Свернуть игру (Fn+Enter)')
                self._swallow_enter = True   # в игру Start не отдаём
                fn_used = True
            elif new:
                fn_used = True               # слой одноразовый: расходуется любой клавишей
        if fn_used:
            self._fn = False

        self._kb[0xFF1B] = held(0)      # Esc
        if not held(35):
            self._swallow_enter = False  # отпустили — снова обычный Start
        self._kb[0xFF0D] = held(35) and not self._swallow_enter   # Enter → Start
        self._kb[0x0020] = held(47)     # Space → Select
        self._kb[0xFF51] = held(24)     # влево
        self._kb[0xFF52] = held(25)     # вверх
        self._kb[0xFF54] = held(36)     # вниз
        self._kb[0xFF53] = held(37)     # вправо

    def _run(self, *cmd):
        """Команда рабочего стола: гашение экрана, свернуть окна."""
        try:
            env = dict(os.environ)
            env.setdefault('DISPLAY', ':0')
            env.setdefault('XAUTHORITY', '/home/orangepi/.Xauthority')
            subprocess.run(list(cmd), capture_output=True, env=env)
        except Exception as e:
            print('[game] команда не выполнена:', e)

    def _map(self, code):
        return {
            0x0D: 0xFF0D,    # Enter → Start
            0x20: 0x0020,    # Space → Select
            0x1B: 0xFF1B,    # Esc → выход
        }.get(code)

    # ── GPIO → A/B ──
    def _gpio(self):
        mapping = [(96, 0xFF08), (131, 0x30)]
        for line, keysym in mapping:
            v = self._req.get_value(line)
            pressed = (v == self._gv.INACTIVE)  # pull-up: INACTIVE(0) = нажата
            if pressed != (self._gpio_state[line] == 0):
                self.key(keysym, pressed)
                self._gpio_state[line] = 0 if pressed else 1

    def run(self):
        print('[game] bridge started (joystick=arrows, GPIO=A/B, CardKB=Start/Select/Esc)')
        while True:
            self._joy()
            self._cardkb()
            self._gpio()
            time.sleep(0.010)

    def cleanup(self):
        self.release_all()
        self._kb_mode(0)          # возвращаем клавиатуре обычный режим
        try:
            os.close(self.fd)
        except Exception:
            pass
        self.disp.close()


if __name__ == '__main__':
    import signal
    os.environ.setdefault('DISPLAY', ':0')
    b = GameInput()

    def _term(sig, frm):
        print('[game] SIGTERM — clean exit')
        try:
            b.cleanup()
        except Exception as e:
            print('[game] cleanup err:', e)
        os._exit(0)

    signal.signal(signal.SIGTERM, _term)
    try:
        b.run()
    except KeyboardInterrupt:
        b.cleanup()
