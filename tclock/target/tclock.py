#!/usr/bin/env python3
"""A standard-library Python translation of Fortio's tclock program.

Original Go program: Copyright 2025 Fortio Authors, Apache-2.0.
This translation retains the clock, countdown, animation, and tailing features.
Run ``python tclock.py --help`` for usage.
"""

from __future__ import annotations

import argparse
import colorsys
import math
import os
import queue
import re
import shutil
import signal
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import IO


CSI = "\x1b["
RESET = f"{CSI}0m"
HIDE_CURSOR = f"{CSI}?25l"
SHOW_CURSOR = f"{CSI}?25h"
CLEAR_HOME = f"{CSI}2J{CSI}H"

RGB = tuple[int, int, int]

NAMED_COLORS: dict[str, RGB | None] = {
    "none": None,
    "black": (0, 0, 0),
    "red": (220, 50, 47),
    "green": (80, 180, 80),
    "yellow": (235, 190, 40),
    "orange": (240, 130, 35),
    "blue": (55, 120, 220),
    "purple": (175, 80, 200),
    "cyan": (45, 190, 190),
    "gray": (150, 150, 150),
    "darkgray": (80, 80, 80),
    "brightred": (255, 80, 80),
    "brightgreen": (90, 240, 100),
    "brightyellow": (255, 245, 95),
    "brightblue": (110, 160, 255),
    "brightpurple": (220, 130, 255),
    "brightcyan": (115, 245, 245),
    "white": (255, 255, 255),
}

# Each digit is four columns wide and five rows high, matching bignum/bignum.go.
DIGITS: dict[str, tuple[str, str, str, str, str]] = {
    "0": (" ━━ ", "┃  ┃", "    ", "┃  ┃", " ━━ "),
    "1": ("   ┃", "   ┃", "    ", "   ┃", "   ┃"),
    "2": (" ━━ ", "   ┃", " ━━ ", "┃   ", " ━━ "),
    "3": (" ━━ ", "   ┃", " ━━ ", "   ┃", " ━━ "),
    "4": ("┃  ┃", " ━━ ", "   ┃", "    ", "   ┃"),
    "5": (" ━━ ", "┃   ", " ━━ ", "   ┃", " ━━ "),
    "6": (" ━━ ", "┃   ", " ━━ ", "┃  ┃", " ━━ "),
    "7": (" ━━ ", "   ┃", "    ", "   ┃", "   ┃"),
    "8": (" ━━ ", "┃  ┃", " ━━ ", "┃  ┃", " ━━ "),
    "9": (" ━━ ", "┃  ┃", " ━━ ", "   ┃", " ━━ "),
}


def parse_bool(value: str) -> bool:
    value = value.lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def parse_color(value: str) -> RGB | None:
    """Parse a named color, RRGGBB hex color, or hue,saturation,lightness."""
    value = value.strip().lower()
    if value in NAMED_COLORS:
        return NAMED_COLORS[value]
    if re.fullmatch(r"[0-9a-f]{6}", value):
        return tuple(int(value[offset : offset + 2], 16) for offset in (0, 2, 4))  # type: ignore[return-value]
    parts = value.split(",")
    if len(parts) == 3:
        try:
            hue, saturation, lightness = (float(part) for part in parts)
            if not all(0 <= part <= 1 for part in (hue, saturation, lightness)):
                raise ValueError
            red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
            return (round(red * 255), round(green * 255), round(blue * 255))
        except ValueError as error:
            raise argparse.ArgumentTypeError(f"invalid color: {value}") from error
    raise argparse.ArgumentTypeError(f"invalid color: {value}")


def mix(first: RGB, second: RGB, amount: float) -> RGB:
    amount = max(0.0, min(1.0, amount))
    return tuple(round(a + (b - a) * amount) for a, b in zip(first, second))  # type: ignore[return-value]


def ansi_color(color: RGB | None, background: bool, truecolor: bool) -> str:
    if color is None:
        # Restore the terminal default for the channel. This matters just outside
        # a disc, where an ANSI background set by the previous cell would linger.
        return f"{CSI}{49 if background else 39}m"
    if truecolor:
        return f"{CSI}{48 if background else 38};2;{color[0]};{color[1]};{color[2]}m"
    # 6x6x6 ANSI 256-color cube.
    index = 16 + 36 * round(color[0] / 255 * 5) + 6 * round(color[1] / 255 * 5) + round(color[2] / 255 * 5)
    return f"{CSI}{48 if background else 38};5;{index}m"


def big_number_lines(value: str, blink: bool = False) -> list[str]:
    colon = ("    ", " .. ", "    ", " .. ", "    ") if blink else ("    ", " :: ", "    ", " :: ", "    ")
    lines = ["" for _ in range(5)]
    for character in value:
        glyph = DIGITS.get(character, colon)
        for row, fragment in enumerate(glyph):
            lines[row] += fragment
    return lines


def parse_duration(value: str) -> timedelta:
    """Parse Go-style durations, adding d (days) and w (weeks)."""
    units = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    pieces = list(re.finditer(r"([+-]?\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h|d|w)", value.strip()))
    if not pieces or "".join(piece.group(0) for piece in pieces) != value.strip():
        raise argparse.ArgumentTypeError("duration must use units such as 5m, 3w2d10h, or 1.5s")
    return timedelta(seconds=sum(float(piece.group(1)) * units[piece.group(2)] for piece in pieces))


def parse_until(value: str, now: datetime) -> datetime:
    value = value.strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%H:%M:%S", "%H:%M", "%I:%M%p", "%I:%M %p"):
        try:
            parsed = datetime.strptime(value.lower(), pattern)
        except ValueError:
            continue
        if "%Y" in pattern:
            return parsed
        if pattern == "%Y-%m-%d":
            return parsed
        candidate = now.replace(hour=parsed.hour, minute=parsed.minute, second=parsed.second, microsecond=0)
        return candidate if candidate > now else candidate + timedelta(days=1)
    raise argparse.ArgumentTypeError("use YYYY-MM-DD HH:MM:SS, YYYY-MM-DD, HH:MM[:SS], or H:MM am/pm")


def duration_text(remaining: timedelta, include_seconds: bool) -> str:
    seconds = max(0, round(remaining.total_seconds()))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        result = f"{days:02d}:{hours:02d}:{minutes:02d}"
    elif hours:
        result = f"{hours:02d}:{minutes:02d}"
    else:
        result = f"{minutes:02d}"
    return f"{result}:{seconds:02d}" if include_seconds else result


@dataclass
class Cell:
    character: str = " "
    foreground: RGB | None = None
    background: RGB | None = None


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.cells = [[Cell() for _ in range(self.width)] for _ in range(self.height)]

    def put(self, x: int, y: int, character: str, foreground: RGB | None = None, background: RGB | None = None) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            cell = self.cells[y][x]
            if character != " ":
                cell.character = character
                cell.foreground = foreground
            if background is not None:
                cell.background = background

    def text(self, x: int, y: int, value: str, foreground: RGB | None) -> None:
        for offset, character in enumerate(value):
            self.put(x + offset, y, character, foreground)

    def box(self, x: int, y: int, width: int, height: int, color: RGB | None) -> None:
        if width < 2 or height < 2:
            return
        self.put(x, y, "╭", color)
        self.put(x + width - 1, y, "╮", color)
        self.put(x, y + height - 1, "╰", color)
        self.put(x + width - 1, y + height - 1, "╯", color)
        for column in range(x + 1, x + width - 1):
            self.put(column, y, "─", color)
            self.put(column, y + height - 1, "─", color)
        for row in range(y + 1, y + height - 1):
            self.put(x, row, "│", color)
            self.put(x + width - 1, row, "│", color)

    def disc(self, center_x: int, center_y: int, radius_x: int, radius_y: int, color: RGB, aliasing: float) -> None:
        """Draw a soft elliptical background disc, similar to AnsiPixels.DiscBlendFN."""
        radius_x = max(1, radius_x)
        radius_y = max(1, radius_y)
        for y in range(max(0, center_y - radius_y), min(self.height, center_y + radius_y + 1)):
            for x in range(max(0, center_x - radius_x), min(self.width, center_x + radius_x + 1)):
                distance = math.sqrt(((x - center_x) / radius_x) ** 2 + ((y - center_y) / radius_y) ** 2)
                if distance <= 1:
                    # High aliasing creates a more pronounced soft/spherical edge.
                    alpha = 1 - distance * (0.4 + 0.6 * aliasing)
                    self.put(x, y, " ", background=mix((0, 0, 0), color, alpha))

    def render(self, truecolor: bool, inverse: bool) -> list[str]:
        lines: list[str] = []
        for row in self.cells:
            foreground: RGB | None = None
            background: RGB | None = None
            result = CSI + "7m" if inverse else ""
            for cell in row:
                if cell.foreground != foreground:
                    result += ansi_color(cell.foreground, False, truecolor)
                    foreground = cell.foreground
                if cell.background != background:
                    result += ansi_color(cell.background, True, truecolor)
                    background = cell.background
                result += cell.character
            lines.append(result + RESET)
        return lines


@dataclass
class Config:
    use_24_hour: bool
    analog: bool
    aa: bool
    aliasing: float
    black_background: bool
    bounce_speed: int
    breath: bool
    boxed: bool
    color: RGB | None
    color_box: RGB | None
    color_disc: RGB | None
    continuous: bool
    debug: bool
    fps: float
    inverse: bool
    no_blink: bool
    no_seconds: bool
    radius: float
    text: str
    truecolor: bool


def digital_canvas(value: str, blink: bool, config: Config, terminal_width: int, terminal_height: int, frame: int) -> Canvas:
    glyphs = big_number_lines(value, blink)
    content_width = max(map(len, glyphs))
    content_height = len(glyphs)
    requested_radius = max(2, 2 * round(config.radius * content_width / 4)) if config.color_disc else 1
    horizontal_margin = min(requested_radius, max(1, (terminal_width - content_width) // 2))
    vertical_margin = min(max(1, requested_radius // 2), max(1, (terminal_height - content_height - 2) // 2))
    extra_text_rows = 2 if config.text else 0
    canvas = Canvas(content_width + horizontal_margin * 2, content_height + vertical_margin * 2 + extra_text_rows)
    content_x = horizontal_margin
    content_y = vertical_margin
    if config.color_disc:
        pulse = 1 + (0.08 * triangle(frame // 7, 10) / 10 if config.breath else 0)
        canvas.disc(canvas.width // 2, content_y + content_height // 2, round(horizontal_margin * pulse), round(vertical_margin * pulse), config.color_disc, config.aliasing)
    if config.boxed:
        box_color = config.color_box if config.color_box is not None else config.color
        canvas.box(content_x - 1, content_y - 1, content_width + 2, content_height + 2, box_color)
    digit_color = breathing_color(config, frame)
    for row, line in enumerate(glyphs):
        canvas.text(content_x, content_y + row, line, digit_color)
    if config.text:
        x = max(0, (canvas.width - len(config.text)) // 2)
        canvas.text(x, content_y + content_height + 1, config.text, digit_color)
    return canvas


def triangle(frame: int, maximum: int) -> int:
    value = frame % (2 * maximum)
    return value if value < maximum else 2 * maximum - 1 - value


def breathing_color(config: Config, frame: int) -> RGB | None:
    if not config.breath or config.color is None:
        return config.color
    return mix((0, 0, 0), config.color, 0.15 + 0.85 * triangle(frame, 100) / 100)


def draw_line(canvas: Canvas, x0: int, y0: int, x1: int, y1: int, character: str, color: RGB | None) -> None:
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        canvas.put(x0, y0, character, color)
        if x0 == x1 and y0 == y1:
            return
        twice_error = 2 * error
        if twice_error >= dy:
            error += dy
            x0 += sx
        if twice_error <= dx:
            error += dx
            y0 += sy


def analog_canvas(now: datetime, config: Config, terminal_width: int, terminal_height: int) -> Canvas:
    # Terminal cells are approximately twice as high as they are wide, so Y is scaled by 1/2.
    radius = max(4, min((terminal_width - 4) // 2, terminal_height - 4))
    width, height = radius * 2 + 3, radius + 3
    canvas = Canvas(width, height)
    center_x, center_y = width // 2, height // 2
    if config.color_disc:
        canvas.disc(center_x, center_y, radius + 1, max(1, radius // 2 + 1), config.color_disc, config.aliasing)

    def coordinate(value: float, maximum: float, length: float) -> tuple[int, int]:
        angle = 2 * math.pi * (maximum - value) / maximum
        return (round(center_x - math.sin(angle) * length), round(center_y - math.cos(angle) * length / 2))

    marker_color: RGB = (255, 255, 255)
    for tick in range(60):
        x, y = coordinate(float(tick), 60, radius)
        if tick % 5 == 0:
            label = str((tick // 5) or 12)
            canvas.text(x - len(label) // 2, y, label, marker_color)
        elif not config.no_seconds:
            canvas.put(x, y, "·" if not config.aa else "⠂", marker_color)

    seconds = now.second + now.microsecond / 1_000_000 if config.continuous else now.second
    minute = now.minute + seconds / 60
    hour = now.hour % 12 + minute / 60
    if not config.no_seconds:
        draw_line(canvas, center_x, center_y, *coordinate(seconds, 60, radius * 0.90), "·", (80, 128, 80))
    draw_line(canvas, center_x, center_y, *coordinate(minute, 60, radius * 0.80), "━", (44, 89, 212))
    draw_line(canvas, center_x, center_y, *coordinate(hour, 12, radius * 0.47), "━", (255, 167, 10))
    canvas.put(center_x, center_y, "●", breathing_color(config, 0))
    return canvas


class KeyReader:
    """Non-blocking single-key reader for q/a/c controls on Windows and POSIX."""
    def __init__(self) -> None:
        self.enabled = sys.stdin.isatty()
        self._old_settings = None
        self._fd: int | None = None

    def __enter__(self) -> KeyReader:
        if not self.enabled or os.name == "nt":
            return self
        try:
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._old_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        except (ImportError, OSError):
            self.enabled = False
        return self

    def __exit__(self, *_: object) -> None:
        if self._old_settings is not None and self._fd is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)

    def read(self) -> str | None:
        if not self.enabled:
            return None
        if os.name == "nt":
            import msvcrt

            return msvcrt.getwch() if msvcrt.kbhit() else None
        import select

        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None


class TailReader:
    def __init__(self, source: IO[str], follow: bool) -> None:
        self.lines: deque[str] = deque(maxlen=200)
        self._source = source
        self._follow = follow
        self._stopped = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self._stopped.set()

    def _read(self) -> None:
        while not self._stopped.is_set():
            line = self._source.readline()
            if line:
                self.lines.append(line.rstrip("\r\n"))
            elif self._follow:
                time.sleep(0.1)
            else:
                return


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Large terminal clock (Python translation of tclock).")
    parser.add_argument("digits", nargs="?", help="Render these digits once, or '-' to tail standard input.")
    parser.add_argument("-24", dest="use_24_hour", action="store_true", help="Use 24-hour time.")
    parser.add_argument("-aa", action="store_true", help="Use the smoother Unicode analog-clock style.")
    parser.add_argument("-aliasing", type=float, default=0.8, help="Disc softness from 0.0 to 1.0 (default: 0.8).")
    parser.add_argument("-analog", action="store_true", help="Show an analog clock.")
    parser.add_argument("-black-bg", dest="black_background", action="store_true", help="Use a black terminal background.")
    parser.add_argument("-bounce", type=int, default=0, help="Bounce speed; zero disables bouncing.")
    parser.add_argument("-box", dest="boxed", action="store_true", help="Draw a rounded outline around the time.")
    parser.add_argument("-breath", action="store_true", help="Pulse the clock color.")
    parser.add_argument("-c", dest="continuous", action="store_true", help="Continuously update analog mode.")
    parser.add_argument("-color", default="red", help="Named color, RRGGBB, or hue,saturation,lightness.")
    parser.add_argument("-color-box", default="", help="Color of the box around the clock.")
    parser.add_argument("-color-disc", default="E0C020", help="Color of the disc behind the clock; use '' to disable.")
    parser.add_argument("-countdown", type=parse_duration, help="Countdown duration, e.g. 3w2d10h.")
    parser.add_argument("-debug", action="store_true", help="Show terminal dimensions beneath the clock.")
    parser.add_argument("-fps", type=float, default=30.0, help="Maximum frames per second in continuous mode.")
    parser.add_argument("-inverse", action="store_true", help="Invert foreground and background.")
    parser.add_argument("-linear", action="store_true", help="Accepted for Go CLI compatibility; disc blending is already linear.")
    parser.add_argument("-no-blink", dest="no_blink", action="store_true", help="Do not blink the digital colon.")
    parser.add_argument("-no-seconds", dest="no_seconds", action="store_true", help="Hide seconds.")
    parser.add_argument("-radius", type=float, default=1.2, help="Disc radius relative to the clock width.")
    parser.add_argument("-tail", help="Tail this file, or '-' for standard input.")
    parser.add_argument("-text", default="", help="Text beneath the clock; use 'none' to hide it.")
    parser.add_argument("-truecolor", nargs="?", const=True, default=True, type=parse_bool, help="Use 24-bit colors (default: true).")
    parser.add_argument("-until", help="Countdown target: date, time, or date/time.")
    return parser


def terminal_size() -> tuple[int, int]:
    size = shutil.get_terminal_size((100, 30))
    return size.columns, size.lines


def format_clock(now: datetime, use_24_hour: bool, no_seconds: bool) -> str:
    result = now.strftime("%H:%M" if use_24_hour else "%I:%M")
    return result if no_seconds else result + now.strftime(":%S")


def emit_frame(rows: list[str], canvas_width: int, config: Config, terminal_width: int, terminal_height: int, frame: int, tail: TailReader | None) -> None:
    if tail is not None:
        # As in the Go program's Tail mode, keep the clock in the upper-right
        # corner while the incoming log text stays below it.
        clock_left = max(0, terminal_width - canvas_width)
        output = [" " * clock_left + row for row in rows] + [RESET] + list(tail.lines)[-(terminal_height - len(rows) - 1) :]
    else:
        if config.bounce_speed > 0:
            max_x = max(0, terminal_width - canvas_width)
            max_y = max(0, terminal_height - len(rows))
            phase = max(1, config.bounce_speed)
            left = triangle(frame // phase, max_x + 1) if max_x else 0
            top = triangle(frame // phase, max_y + 1) if max_y else 0
        else:
            left = max(0, (terminal_width - canvas_width) // 2)
            top = max(0, (terminal_height - len(rows)) // 2)
        output = [""] * top + [" " * left + row for row in rows]
    background = ansi_color((0, 0, 0), True, config.truecolor) if config.black_background else ""
    sys.stdout.write(CLEAR_HOME + background + "\n".join(output) + RESET)
    sys.stdout.flush()


def run_clock(config: Config, end: datetime | None, tail: TailReader | None) -> int:
    frame = 0
    last_display = ""
    key_reader = KeyReader()
    if tail is not None:
        tail.start()
    try:
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.flush()
        with key_reader:
            while True:
                now = datetime.now()
                if end is not None:
                    remaining = end - now
                    if remaining.total_seconds() < 0:
                        sys.stdout.write(f"{CSI}H\aTime's up reached at {format_clock(now, config.use_24_hour, config.no_seconds)}\r\n")
                        return 0
                    display = duration_text(remaining, not config.no_seconds)
                else:
                    display = format_clock(now, config.use_24_hour, config.no_seconds)

                key = key_reader.read()
                if key in {"q", "Q", "\x03"}:
                    return 1 if end is not None else 0
                if key in {"a", "A"}:
                    config.aa = not config.aa
                    config.analog = not config.aa
                    last_display = ""
                if key in {"c", "C"}:
                    config.continuous = not config.continuous
                    last_display = ""

                width, height = terminal_size()
                should_draw = display != last_display or config.breath or config.continuous or tail is not None
                if should_draw:
                    if config.analog or config.aa:
                        canvas = analog_canvas(now, config, width, height)
                    else:
                        canvas = digital_canvas(display, not config.no_blink and now.second % 2 == 1, config, width, height, frame)
                    rows = canvas.render(config.truecolor, config.inverse)
                    if config.debug:
                        rows.append(f"Terminal: {width}x{height}{RESET}")
                    emit_frame(rows, canvas.width, config, width, height, frame, tail)
                    last_display = display
                    frame += 1
                time.sleep(1 / max(1, config.fps) if (config.continuous or config.breath or tail is not None) else 0.05)
    except KeyboardInterrupt:
        return 1 if end is not None else 0
    finally:
        if tail is not None:
            tail.stop()
        sys.stdout.write(RESET + SHOW_CURSOR + "\n")
        sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    # The original Go program uses Unicode box-drawing characters. Explicit UTF-8
    # avoids a cp1252 encoding failure in legacy Windows PowerShell sessions.
    if os.name == "nt" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = make_parser()
    arguments = sys.argv[1:] if argv is None else argv
    if arguments == ["help"]:
        parser.print_help()
        return 0
    args = parser.parse_args(arguments)
    if args.countdown is not None and args.until is not None:
        parser.error("-countdown and -until cannot be used together")
    if args.digits not in (None, "-") and (not args.digits or not args.digits[0].isdigit()):
        parser.error("digits must begin with a numeral")
    if args.aliasing < 0 or args.aliasing > 1:
        parser.error("-aliasing must be between 0 and 1")
    if args.radius < 0:
        parser.error("-radius cannot be negative")
    if args.fps <= 0:
        parser.error("-fps must be greater than zero")

    try:
        color = parse_color(args.color)
        color_box = parse_color(args.color_box) if args.color_box else None
        color_disc = parse_color(args.color_disc) if args.color_disc else None
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))
    text = "" if args.text == "none" else args.text
    if args.countdown is not None and not text:
        now = datetime.now()
        text = "Countdown to " + (now + args.countdown).strftime("%Y-%m-%d %H:%M" if args.use_24_hour else "%Y-%m-%d %I:%M %p")
    config = Config(
        use_24_hour=args.use_24_hour,
        analog=args.analog,
        aa=args.aa,
        aliasing=args.aliasing,
        black_background=args.black_background,
        bounce_speed=args.bounce,
        breath=args.breath,
        boxed=args.boxed or bool(args.color_box),
        color=color,
        color_box=color_box,
        color_disc=color_disc,
        continuous=args.continuous,
        debug=args.debug,
        fps=args.fps,
        inverse=args.inverse,
        no_blink=args.no_blink,
        no_seconds=args.no_seconds,
        radius=args.radius,
        text=text,
        truecolor=args.truecolor,
    )

    # The original program prints one static large number if it receives digits.
    if args.digits not in (None, "-"):
        print("\n".join(big_number_lines(args.digits)))
        return 0

    end: datetime | None = None
    try:
        if args.countdown is not None:
            end = datetime.now() + args.countdown
        elif args.until:
            end = parse_until(args.until, datetime.now())
            if not text:
                text = "Countdown to " + end.strftime("%Y-%m-%d %H:%M" if args.use_24_hour else "%Y-%m-%d %I:%M %p")
                config.text = text
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))

    tail: TailReader | None = None
    opened_file: IO[str] | None = None
    tail_name = "-" if args.digits == "-" else args.tail
    if tail_name:
        if tail_name == "-":
            tail = TailReader(sys.stdin, follow=False)
        else:
            try:
                opened_file = open(tail_name, "r", encoding="utf-8", errors="replace")
            except OSError as error:
                parser.error(f"cannot open tail file: {error}")
            tail = TailReader(opened_file, follow=True)
    try:
        return run_clock(config, end, tail)
    finally:
        if opened_file is not None:
            opened_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
