"""Clipboard copy via Win32 API with a lazy tkinter singleton fallback."""

from __future__ import annotations

import sys

_tk_root = None

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _copy_text_win32(text: str) -> bool:
    if sys.platform != "win32":
        return False

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h_global:
                return False
            locked = kernel32.GlobalLock(h_global)
            if not locked:
                kernel32.GlobalFree(h_global)
                return False
            try:
                ctypes.memmove(locked, data, len(data))
            finally:
                kernel32.GlobalUnlock(h_global)
            if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
                kernel32.GlobalFree(h_global)
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        return False


def _get_tk_root():
    global _tk_root
    if _tk_root is None:
        import tkinter as tk

        _tk_root = tk.Tk()
        _tk_root.withdraw()
    return _tk_root


def _copy_text_tk(text: str) -> bool:
    try:
        root = _get_tk_root()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update_idletasks()
        return True
    except Exception:
        return False


def copy_text(text: str) -> bool:
    if _copy_text_win32(text):
        return True
    return _copy_text_tk(text)
