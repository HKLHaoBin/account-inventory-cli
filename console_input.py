"""Console keyboard helpers: VT mode, non-blocking key detection, arrow keys."""

from __future__ import annotations

import sys

_IS_WINDOWS = sys.platform == "win32"


def enable_vt_mode() -> bool:
    if not _IS_WINDOWS:
        return False

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        std_output_handle = -11
        enable_virtual_terminal_processing = 0x0004
        handle = kernel32.GetStdHandle(std_output_handle)
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        new_mode = mode.value | enable_virtual_terminal_processing
        return bool(kernel32.SetConsoleMode(handle, new_mode))
    except Exception:
        return False


def keyboard_supported() -> bool:
    return _IS_WINDOWS


def kbhit() -> bool:
    if not _IS_WINDOWS:
        return False

    try:
        import msvcrt

        return bool(msvcrt.kbhit())
    except Exception:
        return False


def _read_line_unix(prompt: str = "") -> str | None:
    """Read one line on Unix. Esc returns None; Ctrl+C raises KeyboardInterrupt."""
    import termios
    import tty

    if prompt:
        print(prompt, end="", flush=True)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    chars: list[str] = []
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                print()
                return None
            if ch in ("\r", "\n"):
                print()
                return "".join(chars).strip()
            if ch in ("\x08", "\x7f"):
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif len(ch) == 1:
                chars.append(ch)
                print(ch, end="", flush=True)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def read_command_line(prompt: str = "命令 > ") -> str | None:
    """Read a command line. Esc returns None; Ctrl+C raises KeyboardInterrupt."""
    if not _IS_WINDOWS:
        return _read_line_unix(prompt)

    print(prompt, end="", flush=True)
    chars: list[str] = []
    while True:
        key = read_key()
        if key == "esc":
            print()
            return None
        if key == "enter":
            print()
            return "".join(chars).strip()
        if key == "backspace":
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
        elif len(key) == 1 and key not in ("unknown",):
            chars.append(key)
            print(key, end="", flush=True)


def read_line_or_exit(prompt: str = "") -> str | None:
    """Read one line. Esc returns None; Ctrl+C raises KeyboardInterrupt."""
    if not _IS_WINDOWS:
        return _read_line_unix(prompt)

    if prompt:
        print(prompt, end="", flush=True)
    chars: list[str] = []
    while True:
        key = read_key()
        if key == "esc":
            print()
            return None
        if key == "enter":
            print()
            return "".join(chars).strip()
        if key == "backspace":
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
        elif len(key) == 1 and key not in ("unknown",):
            chars.append(key)
            print(key, end="", flush=True)


def read_key(timeout: float | None = None) -> str:
    del timeout  # reserved for future use; msvcrt has no timeout API

    if not _IS_WINDOWS:
        raise OSError("Keyboard input is not supported on this platform")

    import msvcrt

    ch = msvcrt.getch()
    if ch in (b"\xe0", b"\x00"):
        code = msvcrt.getch()
        if code == b"H":
            return "up"
        if code == b"P":
            return "down"
        return "unknown"

    try:
        char = ch.decode("utf-8", errors="ignore")
    except Exception:
        char = ""

    if char in ("\x08", "\x7f"):
        return "backspace"
    if char == " ":
        return "space"
    if char in ("\r", "\n"):
        return "enter"
    if char == ":":
        return ":"
    if char.lower() == "y":
        return "y"
    if char.lower() == "n":
        return "n"
    if char == "\x1b":
        return "esc"
    return char or "unknown"
