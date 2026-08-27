"""Aero / DWM glass for the launcher window — pure ctypes, zero dependencies.

Public API:
    apply_aero(hwnd: int, dark: bool = True, tint: int = 0xCC14120A) -> bool

What it does (best effort, every step fails safe -> never raises):
  1. DwmExtendFrameIntoClientArea  margins {0, 0, 1, 0}  — hairline glass sheet
     (Win7+, silently skipped when dwmapi is unavailable / composition off).
  2. DwmSetWindowAttribute DWMWA_USE_IMMERSIVE_DARK_MODE (20, fallback 19)
     — dark titlebar + caption buttons on Win10 1809+ / Win11.
  3. SetWindowCompositionAttribute ACCENT_ENABLE_BLURBEHIND with an ABGR tint
     — blurred "classic expensive" backdrop behind the client area (Win10+;
     on Win7/8 the call simply fails and is ignored).

Returns True when at least one effect was applied, False for a clean no-op
(unsupported OS, non-Windows, offscreen/fake hwnd, stripped-down Wine...).
"""
from __future__ import annotations

import sys

# --- constants (mirrored from winuser.h / dwmapi.h) --------------------------
WCA_ACCENT_POLICY = 19
ACCENT_ENABLE_BLURBEHIND = 3
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # pre-1903 builds


def apply_aero(hwnd: int, dark: bool = True, tint: int = 0xCC14120A) -> bool:
    """Apply DWM glass + dark titlebar + blur-behind accent to a native hwnd.

    Safe to call once from MainWindow.showEvent. Never raises; returns True
    if any effect stuck so callers may log/ignore as they see fit.
    """
    if sys.platform != 'win32' or not hwnd:
        return False
    ok = False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL('user32', use_last_error=True)
        dwmapi = ctypes.WinDLL('dwmapi', use_last_error=True)

        # 1) glass frame sheet — extend frame 1px into the client area
        class _MARGINS(ctypes.Structure):
            _fields_ = [('cxLeftWidth', wintypes.INT),
                        ('cxRightWidth', wintypes.INT),
                        ('cyTopHeight', wintypes.INT),
                        ('cyBottomHeight', wintypes.INT)]

        try:
            hr = dwmapi.DwmExtendFrameIntoClientArea(
                wintypes.HWND(hwnd), ctypes.byref(_MARGINS(0, 0, 1, 0)))
            if hr == 0:
                ok = True
        except Exception:
            pass

        # 2) immersive dark titlebar (attr 20 on modern builds, 19 on older)
        val = ctypes.c_int(1 if dark else 0)
        for attr in (DWMWA_USE_IMMERSIVE_DARK_MODE,
                     DWMWA_USE_IMMERSIVE_DARK_MODE_OLD):
            try:
                hr = dwmapi.DwmSetWindowAttribute(
                    wintypes.HWND(hwnd), wintypes.DWORD(attr),
                    ctypes.byref(val), ctypes.sizeof(val))
                if hr == 0:
                    ok = True
                    break
            except Exception:
                continue

        # 3) blur-behind accent with warm ABGR tint (0xCC14120A = panel bg @ 80%)
        class _ACCENT_POLICY(ctypes.Structure):
            _fields_ = [('AccentState', ctypes.c_uint),
                        ('AccentFlags', ctypes.c_uint),
                        ('GradientColor', ctypes.c_uint),
                        ('AnimationId', ctypes.c_uint)]

        class _COMP_ATTR_DATA(ctypes.Structure):
            _fields_ = [('Attribute', ctypes.c_uint),
                        ('Data', ctypes.c_void_p),
                        ('SizeOfData', ctypes.c_size_t)]

        try:
            accent = _ACCENT_POLICY(ACCENT_ENABLE_BLURBEHIND, 0,
                                    tint & 0xFFFFFFFF, 0)
            data = _COMP_ATTR_DATA(
                WCA_ACCENT_POLICY,
                ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p),
                ctypes.sizeof(accent))
            if user32.SetWindowCompositionAttribute(
                    wintypes.HWND(hwnd), ctypes.byref(data)):
                ok = True
        except Exception:
            pass
    except Exception:
        return ok
    return ok
