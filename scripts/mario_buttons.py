#!/usr/bin/env python3
import gpiod, time
from Xlib import display, X
from Xlib.ext import xtest

BUTTONS = [(96, 19), (131, 22)]  # (line, keycode): A=jump "0", B=run Backspace
DEBOUNCE = 0.015

d = display.Display(":0")
chip = gpiod.Chip("gpiochip0")
lines = chip.get_lines([96, 131])
lines.request(consumer="mario-btns", type=gpiod.LINE_REQ_DIR_IN,
              flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP)

state = {96: 1, 131: 1}
last = {96: 0.0, 131: 0.0}

def send(kc, pressed):
    xtest.fake_input(d, X.KeyPress if pressed else X.KeyRelease, kc)
    d.flush()

print("mario-btns: started", flush=True)
try:
    while True:
        vals = lines.get_values()
        now = time.time()
        for (line, kc), v in zip(BUTTONS, vals):
            if v != state[line] and (now - last[line]) >= DEBOUNCE:
                send(kc, pressed=(v == 0))
                print("BTN line=%d -> %s" % (line, "PRESS" if v == 0 else "RELEASE"), flush=True)
                state[line] = v
                last[line] = now
        time.sleep(0.01)
except KeyboardInterrupt:
    pass
