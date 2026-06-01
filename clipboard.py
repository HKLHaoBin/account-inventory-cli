"""Clipboard copy via pyperclip with retry."""

from __future__ import annotations

import time

import pyperclip


def _copy_via_pyperclip(text: str) -> None:
    pyperclip.copy(text)


def _paste_via_pyperclip() -> str:
    return pyperclip.paste()


def read_text() -> str | None:
    max_attempts = 5
    base_delay = 0.05
    for attempt in range(max_attempts):
        try:
            return _paste_via_pyperclip()
        except pyperclip.PyperclipException:
            if attempt + 1 >= max_attempts:
                return None
            time.sleep(base_delay * (attempt + 1))
    return None


def copy_text(text: str) -> bool:
    max_attempts = 5
    base_delay = 0.05
    for attempt in range(max_attempts):
        try:
            _copy_via_pyperclip(text)
            return True
        except pyperclip.PyperclipException:
            if attempt + 1 >= max_attempts:
                return False
            time.sleep(base_delay * (attempt + 1))
    return False
