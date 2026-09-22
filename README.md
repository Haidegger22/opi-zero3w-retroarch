# 🎮 RetroArch + M5Stack на Orange Pi Zero 3W

Полноценная игровая консоль на Orange Pi Zero 3W (Allwinner A733, Debian 11 bullseye):

- **RetroArch 1.14.0** + ядро Nestopia (**NES** — Super Mario Bros и другие NES-игры)
- **RetroArch + mGBA** (**Game Boy / GBC / GBA** — Shantae и др., см. [`docs/GBC-GAMEBOY.md`](docs/GBC-GAMEBOY.md))
- **Управление через M5Stack PaHub**: джойстик V2 (движение), CardKB (Start/Select/Esc)
- **2 GPIO-кнопки**, выведенные отдельно на гребёнку (прыжок / бег-огонь) — удобные отдельные кнопки
- **Удержание стрелок на CardKB** работает: клавиатура перепрошита официальной прошивкой M5Stack с режимом
  сканирования нажатий (раньше она сообщала только отжатие — см. раздел ниже)

> 🏆 **Важно для всех core'ов:** на Zero 3W с GPU PowerVR у RetroArch рабочий видео-драйвер — **`xvideo`** (`gl` падает с segfault на шейдерах, `sdl2` даёт чёрный экран). Подробности в `docs/GBC-GAMEBOY.md` → «Проблемы».

---

## 🔩 Железо

| Компонент | I2C-адрес | Канал PaHub | Роль в игре |
|-----------|-----------|-------------|-------------|
| PaHub v1.1 (мультиплексор) | 0x70 | — | разводка шины на 4 канала |
| Joystick V2 | 0x63 | CH0 | движение (← → ↑ ↓) |
| Scroll | 0x40 | CH1 | (не используется в игре) |
| CardKB v1.1 | 0x5F | CH2 | Enter=Start, Space=Select, Esc=выход |
| Кнопка A (GPIO) | пин 22 = PD0 = GPIO 96 | — | прыжок |
| Кнопка B (GPIO) | пин 21 = MISO.3 = GPIO 131 | — | бег / огонь |
| GND (общий для кнопок) | пин 20 | — | — |

> ⚠️ **Важно про питание:** вентилятор и другая периферия НЕ должны питаться от того же источника, что и PaHub — иначе помехи заливают I2C-шину (симптом: пачки `twi_sunxi: Bus error` в dmesg, джойстик «замирает»). Вентилятор питаем от 5V/GND гребёнки отдельно.

---

## 📦 Шаг 1. Базовая система

```bash
# Debian 11 bullseye (arm64) — Orange Pi OS / Armbian
sudo apt update && sudo apt upgrade -y

# Зависимости
sudo apt install -y python3 python3-xlib xdotool gpiod python3-libgpiod \
    libsdl2-2.0-0 libasound2 libpulse0 git curl

# Проверка I2C
ls /dev/i2c-0   # должен существовать
```

---

## 🕹️ Шаг 2. Установка RetroArch 1.14.0

В Debian bullseye в репозитории только **RetroArch 1.7.3** (ноябрь 2020) — в нём баг SDL2-драйвера: клавиатура срабатывает на **отпускание**, а не на нажатие. Нужен **1.14.0** из backports.

Зеркала huaweicloud/deb.debian.org для backports мёртвы (404), поэтому используем **archive.debian.org**:

```bash
# Добавляем backports (в /etc/apt/sources.list или sources.list.d/)
echo "deb http://archive.debian.org/debian bullseye-backports main contrib non-free" | \
    sudo tee /etc/apt/sources.list.d/backports.list

# (необязательно) чтобы apt не ругался на устаревший архив
echo 'Acquire::Check-Valid-Until "false";' | sudo tee /etc/apt/apt.conf.d/99no-check-valid-until

sudo apt update
sudo apt install -t bullseye-backports retroarch
```

Проверка:
```bash
retroarch --version   # RetroArch v1.14.0
```

---

## 🧩 Шаг 3. PaHub + модули: демон m5hub.py

Демон `m5hub.py` опрашивает все три устройства через PaHub:

- джойстик V2 → курсор мыши + левый клик
- Scroll → прокрутка + клики
- CardKB → QWERTY-клавиатура (US-раскладка)

> 📦 Демон живёт в отдельном репозитории **`Haidegger22/opi-zero3w-m5hub`** (он же системный драйвер для рабочего стола). Здесь он только используется как зависимость.

### Установка

```bash
mkdir -p ~/.openclaw/workspace
cd ~/.openclaw/workspace
# m5hub.py из своего репозитория:
curl -o m5hub.py https://raw.githubusercontent.com/Haidegger22/opi-zero3w-m5hub/main/m5hub.py

# systemd-сервис (автозапуск)
sudo tee /etc/systemd/system/m5hub.service >/dev/null <<'EOF'
[Unit]
Description=M5Stack Hub — Joystick + Scroll + Keyboard
After=graphical.target

[Service]
User=orangepi
WorkingDirectory=/home/orangepi/.openclaw/workspace
ExecStart=/usr/bin/python3 -u m5hub.py
Restart=on-failure
RestartSec=5
Nice=-10

[Install]
WantedBy=graphical.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now m5hub
systemctl status m5hub   # "🟢 Готов" — работает
```

**Калибровка** джойстика происходит автоматически при старте (50 семплов, медиана, отброс выбросов): в логе видно `⚙️ Центр: X=… Y=… (n=50/50)`.

> ℹ️ Улучшения относительно базовой версии: `_g.clear()` после каждого ioctl (нет утечки памяти), калибровка устойчива к I2C-мусору, сброс PaHub при выходе, корректный SIGTERM.

---

## 🔘 Шаг 4. GPIO-кнопки (прыжок / бег)

Клавиатура CardKB в **заводском** виде — «одноразовая»: старая прошивка шлёт код клавиши **один раз** при нажатии и сразу сбрасывается, поэтому в играх всё срабатывало на отпускание. Именно из-за этого прыжок и бег были вынесены на **честные GPIO-кнопки** (уровень «нажата/не нажата» читается напрямую) — они и остаются самыми удобными для этих действий.

**Это исправлено 22.09.2026.** Клавиатура перепрошита официальной прошивкой M5Stack с режимом сканирования нажатий: она отдаёт битовую маску того, что зажато **прямо сейчас**, и стрелки держатся столько, сколько держишь клавишу. Со стороны игр за это отвечает `scripts/game_input.py` (включает режим `0x20 = 1` при старте, читает маску регистра `0x10`, складывает стрелки клавиатуры со стрелками джойстика и возвращает обычный режим на выходе). Подробный разбор прошивки, распиновка и грабли — в README репозитория [`opi-zero3w-m5hub`](https://github.com/Haidegger22/opi-zero3w-m5hub), раздел «Прошивка CardKB через Raspberry Pi 5».

### Подключение

```
GPIO пин 22 (PD0, GPIO 96) ──[кнопка A]──┐
                                         ├── GND (пин 20, общий)
GPIO пин 21 (MISO.3, GPIO 131) ──[кнопка B]──┘
```

- Кнопка 4-ножная: ножки одной стороны соединены между собой. GND на одну пару, GPIO на противоположную.
- Резисторы не нужны — включаем **внутренний pull-up** программно (проверено: на A733 работает).
- Схема: отпущена = `1`, нажата = `0`.

### Права на GPIO (udev-правило)

```bash
sudo cp udev/99-gpio.rules /etc/udev/rules.d/99-gpio.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=gpio
# проверка (должны быть "1 1" при отпущенных кнопках)
gpioget -B pull-up 0 96 131
```

### Проверка кнопок

```bash
python3 scripts/mario_buttons.py   # жми кнопки — видно PRESS/RELEASE
```

---

## 🎮 Шаг 5. Игровой мост game_input.py

Во время игры m5hub **паузится** (освобождает I2C), а управление берёт `scripts/game_input.py` — единый процесс, который читает всё и шлёт события в RetroArch через XTest:

| Источник | Канал/пин | Что шлёт | Клавиша |
|----------|-----------|----------|---------|
| Джойстик V2 | CH0 (0x63) | стрелки ← → ↑ ↓ | left/right/up/down |
| Кнопка A | GPIO 96 | A (прыжок) | `num0` |
| Кнопка B | GPIO 131 | B (бег/огонь) | `Backspace` |
| CardKB | CH2 (0x5F) | Start / Select / Esc | `enter` / `space` / `escape` |

### Snap к доминирующей оси

Джойстик работает как **4-направленный D-pad**: если одна ось в 2+ раза сильнее другой — слабая зануляется (`abs(sdx) > abs(sdy) * 2`). Диагональный наклон даёт только одну стрелку — без ложных диагоналей и «залипаний» между направлениями (важно для танчиков/платформеров).

```bash
cp scripts/game_input.py ~/.openclaw/workspace/game_input.py
```

---

## 🚀 Шаг 6. Лаунчер retrogame.sh

Запускает игру одной иконкой: **пауза m5hub → игровой мост → RetroArch → возврат m5hub**.

```bash
cp scripts/retrogame.sh ~/.openclaw/workspace/retrogame.sh
chmod +x ~/.openclaw/workspace/retrogame.sh
```

Лаунчер использует `sudo systemctl stop/start m5hub` **без пароля** — для этого нужен sudoers-файл:

```bash
echo "orangepi ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop m5hub, /usr/bin/systemctl start m5hub" | \
    sudo tee /etc/sudoers.d/mario
```

Что делает скрипт:
1. Проверяет lock-файл `/tmp/retrogame.lock` (защита от двойного клика)
2. Останавливает m5hub
3. Запускает `game_input.py` в фоне
4. Запускает RetroArch с игрой
5. При выходе: убивает мост, удаляет lock, возвращает m5hub

```bash
# ручной запуск
bash ~/.openclaw/workspace/retrogame.sh
```

---

## ⚙️ Шаг 7. Конфиг RetroArch

```bash
mkdir -p ~/.config/retroarch
cp config/retroarch.cfg ~/.config/retroarch/retroarch.cfg
```

Ключевые строки:

```ini
input_driver = "sdl2"          # ⚠️ НЕ "x" — вызывает segfault/fork-bomb на EGL/PowerVR!
input_player1_a = "num0"       # GPIO кнопка A (прыжок)
input_player1_b = "Backspace"  # GPIO кнопка B (бег/огонь)
input_player1_start = "enter"  # CardKB
input_player1_select = "space" # CardKB
input_player1_up/down/left/right = "up"/"down"/"left"/"right"
input_quit = "escape"
```

---

## 🖥️ Шаг 8. Иконка на рабочем столе

```bash
mkdir -p ~/Desktop
cp config/retrogame.desktop ~/Desktop/retrogame.desktop
chmod +x ~/Desktop/retrogame.desktop
```

Также, чтобы системная иконка «RetroArch» из меню приложений вела на наш лаунчер (а не запускала `retroarch` напрямую — это вызывало конфликт с m5hub):

```bash
mkdir -p ~/.local/share/applications
cp config/retrogame.desktop ~/.local/share/applications/retroarch.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

---

## 🕹️ Итог: как играть

1. Нажми иконку **🎮 RetroArch (NES)** на рабочем столе
2. Джойстик V2 — движение Марио
3. GPIO кнопка A — прыжок, GPIO кнопка B — бег/огонь
4. CardKB: Enter — Start/пауза, Space — Select, Esc — выход
5. После выхода из игры m5hub автоматически возвращается (рабочий стол снова управляется джойстиком)

ROM игры лежит в `~/roms/nes/SuperMarioBros.nes` (путь прописан в лаунчере).

---

## 🔧 Устранение неполадок

| Симптом | Причина / решение |
|---------|-------------------|
| I2C-ошибки пачками (`twi_sunxi Bus error`) | Помехи от питания: вентилятор/периферия питается от PaHub. Перекинуть на 5V/GND гребёнки |
| Джойстик «замирает» | Сканировать шину только при остановленном m5hub (`sudo systemctl stop m5hub`), иначе артефакты |
| RetroArch уходит в fork-bomb (100+ процессов) | Был `input_driver="x"` — вернуть `sdl2`. Лечение: `pkill -9 -x retroarch` |
| Иконка мигает, игра не запускается | Завис lock-файл — удалить: `rm -f /tmp/retrogame.lock` |
| Игра запускается, но клавиши «на отпускание» | Так ведёт себя CardKB (one-shot). Для прыжка/бега — только GPIO-кнопки |
| Кнопки не читаются (Permission denied) | Пересоздать udev-правило, проверить группу `input` |

---

## 📁 Структура репозитория

```
├── README.md                 ← эта инструкция
├── docs/
│   └── GBC-GAMEBOY.md        ← эмуляция Game Boy (mGBA): установка + отладка видео-драйверов
├── scripts/
│   ├── game_input.py         ← игровой мост (джойстик→стрелки, GPIO→A/B, CardKB→Start/Select/Esc)
│   ├── input-supervisor.py   ← сторож ввода: пока игра свёрнута, управление у рабочего стола
│   ├── mario_buttons.py      ← тестер GPIO-кнопок
│   ├── retrogame.sh          ← лаунчер NES
│   ├── retrogame-gbc.sh      ← лаунчер GBC/GBA
│   └── select_game_gbc.py    ← выбор GBC-игры через zenity
├── config/
│   ├── retroarch.cfg         ← конфиг RetroArch (готовые бинды NES)
│   ├── retrogame.desktop     ← иконка NES на рабочий стол
│   ├── gbc.cfg               ← конфиг GBC (видео xvideo + кнопки)
│   └── gbc.desktop           ← иконка GBC на рабочий стол
└── udev/
    └── 99-gpio.rules         ← доступ к GPIO для группы input
```

> ℹ️ `m5hub.py` здесь нет — системный демон живёт в своём репозитории [`Haidegger22/opi-zero3w-m5hub`](https://github.com/Haidegger22/opi-zero3w-m5hub) (см. Шаг 3).

---

## 🔄 Свёрнутая игра больше не отбирает клавиатуру (input-supervisor.py)

Игра и драйвер `m5hub` не могут работать одновременно — они делят шину I2C с
клавиатурой CardKB. Лаунчер останавливает драйвер на время игры и возвращает его
при выходе. **Отсюда и бралась засада:** если игру не закрыть, а свернуть
(`Fn+Enter` / `Ctrl+Alt+D`), лаунчер продолжает ждать её закрытия, драйвер остаётся
выключенным — и на рабочем столе молчат **все три** устройства сразу: джойстик,
скролл и клавиатура (они все висят на одном `m5hub`).

Сторож решает это, следя за окном RetroArch:

| Состояние окна игры | Что делает сторож |
|---|---|
| окно есть, но не отображается (свёрнута) | гасит игровой мост, поднимает `m5hub` → ввод на рабочем столе |
| окно отображается, или окна ещё нет (меню выбора игры) | пауза `m5hub`, поднимает игровой мост → ввод в игре |
| игра закрыта (замок сессии снят) | завершается и уводит свой мост за собой |

Состояние определяется по окну: `xdotool search --class retroarch` плюс `xwininfo`
(`IsViewable` / `IsUnMapped`). Опрос — раз в 2 секунды, реакция мгновенная.

Запускается он из `retrogame.sh` вместо игрового моста: мост теперь его дочерний
процесс, и он же корректно его завершает — мост по SIGTERM снимает с клавиатуры
режим сканирования и отпускает шину I2C.

**Проверка руками:** сверни игру — джойстик, скролл и клавиатура работают на
рабочем столе; разверни игру — снова работают в игре.

---

Сделано на практике: Orange Pi Zero 3W (A733), Debian 11 bullseye, RetroArch 1.14.0 + Nestopia, M5Stack PaHub + Joystick V2 + Scroll + CardKB, 2 GPIO-кнопки.
