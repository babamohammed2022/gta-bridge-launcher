"""GTA Bridge launcher visual system — single source of truth for styling.

Provides the palette (T), the global stylesheet (app_qss), the shared
widget kit (NavButton, ActionButton, heading, body) and the display-font
resolver. app.py and any future UI module import from here instead of
re-coding backgrounds, borders and type rules.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QPushButton


class T:
    # SAS 87 yellow base + Sony Walkman (mid-2005) accents -- dark warm
    # background, yellow headlines/primary CTA, Walkman orange for
    # checked/selected fills and borders, Walkman green for hover lifts,
    # focus rings and positive states. Links stay blue.
    COLOR_DARK_GREEN = "#3d3410"        # border tone (dark olive)
    COLOR_PANEL_BG = "#14120a"          # near-black warm
    COLOR_PANEL_BG_LIGHT = "#241f0e"
    COLOR_TEXT_BRIGHT = "#ffe600"       # yellow headline
    COLOR_TEXT_BODY = "#ffffff"         # white body text
    COLOR_TEXT_DIM = "#9a9270"
    COLOR_GROVE_GREEN = "#c9b800"       # primary button accent (yellow)
    COLOR_WALKMAN_ORANGE = "#e67300"    # checked/selected fills + borders
    COLOR_WALKMAN_GREEN = "#61a60e"     # hover lifts, focus, positive states
    COLOR_SUNSET_ORANGE = "#e67300"     # unified with Walkman orange
    COLOR_SUNSET_PINK = "#ff2bd6"
    COLOR_LCS_AMBER = "#ffb84d"
    COLOR_LINK = "#4aa3ff"              # hyperlink blue -- links stay blue
    COLOR_YELLOW = "#ffe600"
    COLOR_BG_TOP = "#1a1a05"
    COLOR_BG_MID = "#5e4a1f"
    COLOR_BG_HORIZON = "#3a2b0a"
    COLOR_BG_BOTTOM = "#0f0d05"
    COLOR_DANGER = "#ff5b5b"
    COLOR_SUCCESS = "#61a60e"           # positive states -- Walkman green
    # --- surface system (elevation layers) — SAS87 polish pass ---------------
    COLOR_BG = "#0e0c08"                # window base, deepest layer
    COLOR_RAISED = "#1c1810"            # elevated surfaces (inputs, HUD)
    COLOR_BORDER = "#2a2416"            # hairline panel borders
    COLOR_HOVER_BG = "#1f1a10"          # subtle lift on hover
    COLOR_PRESSED_BG = "#0a0906"        # pressed darken
    COLOR_ON_ACCENT = "#04140a"         # text sitting on accent fills
    COLOR_FOCUS = "#6677b900"           # focus ring -- Walkman green @ 40%
    COLOR_CHECKER = "#262218"           # transparency checkerboard (editor)
    COLOR_SCROLL_THUMB = "#2a2416"
    COLOR_SCROLL_THUMB_HOVER = "#4a3f1e"
    DISPLAY_FONT = "Pricedown"  # resolved post-QApp; falls back visually


def _resolve_display_font(app):
    """After QApplication exists, pick the real display font family."""
    from PyQt5.QtGui import QFontDatabase
    fams = set(QFontDatabase().families())
    for cand in ('Pricedown Bl', 'Pricedown'):
        if cand in fams:
            T.DISPLAY_FONT = cand
            return
    T.DISPLAY_FONT = 'Impact'


def app_qss() -> str:
    """Global surface system: three elevation layers + shared control language.

    Layer 0 bg #0e0c08 (window) / layer 1 panel #14120a + 1px #2a2416 border
    / layer 2 raised #1c1810. Vista-crisp geometry: 2px radius on controls,
    3px max on panels, flat solid fills (no gradients), hover = border to
    accent + bg lift, pressed darken, 1px Walkman-green@40% focus ring.
    Per-widget setStyleSheet calls elsewhere intentionally override these.
    """
    return f"""
    QMainWindow, QDialog {{ background: {T.COLOR_BG}; }}
    QLabel {{ color: {T.COLOR_TEXT_BODY}; background: transparent;
        font-kerning: normal; }}
    QToolTip {{
        background: {T.COLOR_RAISED}; color: {T.COLOR_TEXT_BODY};
        border: 1px solid {T.COLOR_BORDER}; border-radius: 2px;
        padding: 4px 8px; font-kerning: normal;
    }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: {T.COLOR_SCROLL_THUMB}; min-height: 24px; border-radius: 2px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {T.COLOR_SCROLL_THUMB_HOVER}; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
    QScrollBar::handle:horizontal {{
        background: {T.COLOR_SCROLL_THUMB}; min-width: 24px; border-radius: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {T.COLOR_SCROLL_THUMB_HOVER}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox {{
        background: {T.COLOR_RAISED}; color: {T.COLOR_TEXT_BODY};
        border: 1px solid {T.COLOR_BORDER}; border-radius: 2px;
        padding: 3px 6px; selection-background-color: {T.COLOR_WALKMAN_ORANGE};
        selection-color: {T.COLOR_ON_ACCENT}; font-kerning: normal;
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {{
        border: 1px solid {T.COLOR_FOCUS};
    }}
    QLineEdit:hover, QSpinBox:hover {{ border: 1px solid {T.COLOR_FOCUS}; }}
    QComboBox {{
        background: {T.COLOR_RAISED}; color: {T.COLOR_TEXT_BODY};
        border: 1px solid {T.COLOR_BORDER}; border-radius: 2px; padding: 3px 8px;
    }}
    QComboBox:hover {{ border: 1px solid {T.COLOR_FOCUS}; }}
    QComboBox:focus {{ border: 1px solid {T.COLOR_FOCUS}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {T.COLOR_PANEL_BG}; color: {T.COLOR_TEXT_BODY};
        border: 1px solid {T.COLOR_BORDER}; border-radius: 2px;
        selection-background-color: {T.COLOR_WALKMAN_ORANGE};
        selection-color: {T.COLOR_ON_ACCENT}; outline: none;
    }}
    QMenu {{
        background: {T.COLOR_PANEL_BG}; color: {T.COLOR_TEXT_BODY};
        border: 1px solid {T.COLOR_BORDER}; border-radius: 2px; padding: 4px;
        font-kerning: normal;
    }}
    QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 2px; }}
    QMenu::item:selected {{
        background: {T.COLOR_WALKMAN_ORANGE}; color: {T.COLOR_ON_ACCENT}; }}
    QMenu::separator {{ height: 1px; background: {T.COLOR_BORDER}; margin: 4px 8px; }}
    QGroupBox {{
        color: {T.COLOR_TEXT_BRIGHT}; border: 1px solid {T.COLOR_BORDER};
        border-radius: 3px; margin-top: 10px; padding-top: 6px; font-weight: 600;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
    QPushButton {{ border-radius: 2px; font-kerning: normal; }}
    QProgressBar {{
        background: {T.COLOR_RAISED}; border: 1px solid {T.COLOR_BORDER};
        border-radius: 2px; text-align: center; color: {T.COLOR_TEXT_BODY};
    }}
    QProgressBar::chunk {{ background: {T.COLOR_WALKMAN_ORANGE}; border-radius: 2px; }}
    QCheckBox {{ color: {T.COLOR_TEXT_BODY}; spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px; border: 1px solid {T.COLOR_BORDER};
        border-radius: 2px; background: {T.COLOR_RAISED};
    }}
    QCheckBox::indicator:checked {{
        background: {T.COLOR_WALKMAN_ORANGE}; border-color: {T.COLOR_WALKMAN_ORANGE};
    }}
    QListWidget {{ alternate-background-color: {T.COLOR_RAISED}; outline: none; }}
    QSlider::groove:horizontal {{
        height: 4px; background: {T.COLOR_BORDER}; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{ background: {T.COLOR_WALKMAN_ORANGE}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: {T.COLOR_TEXT_BRIGHT}; width: 12px; margin: -5px 0;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal:hover {{ background: {T.COLOR_TEXT_BODY}; }}
    """


# =============================================================================
# Shared widgets
# =============================================================================

class NavButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text.upper())
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(44)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {T.COLOR_PANEL_BG};
                color: {T.COLOR_TEXT_BODY};
                border: 1px solid {T.COLOR_BORDER};
                border-left: 4px solid {T.COLOR_BORDER};
                border-radius: 2px;
                font-family: 'Segoe UI Light','Segoe UI';
                font-size: 15px;
                font-weight: 25;
                letter-spacing: 2px;
                font-kerning: normal;
                text-align: left;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                background: {T.COLOR_HOVER_BG};
                border-left: 4px solid {T.COLOR_WALKMAN_GREEN};
            }}
            QPushButton:pressed {{ background: {T.COLOR_PRESSED_BG}; }}
            QPushButton:checked {{
                color: {T.COLOR_ON_ACCENT};
                border-left: 4px solid {T.COLOR_YELLOW};
                background: {T.COLOR_WALKMAN_ORANGE};
            }}
        """)


class ActionButton(QPushButton):
    def __init__(self, text: str, accent: str | None = None, danger: bool = False):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)
        col = T.COLOR_DANGER if danger else (accent or T.COLOR_GROVE_GREEN)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {T.COLOR_PANEL_BG_LIGHT};
                color: {T.COLOR_TEXT_BRIGHT};
                border: 1px solid {col};
                border-radius: 2px;
                padding: 7px 16px;
                font-family: 'Segoe UI';
                font-size: 9pt;
                font-kerning: normal;
            }}
            QPushButton:hover {{ background: {col}; color: {T.COLOR_ON_ACCENT}; }}
            QPushButton:pressed {{ background: {T.COLOR_PRESSED_BG}; color: {T.COLOR_TEXT_DIM}; }}
            QPushButton:disabled {{ color: {T.COLOR_TEXT_DIM}; border-color: {T.COLOR_BORDER}; }}
            QPushButton:focus {{ border: 1px solid {T.COLOR_FOCUS}; }}
        """)


def heading(text: str, size: int = 22, color: str | None = None) -> QLabel:
    """Zune/WP7 section header: Segoe UI Light, uppercase, wide tracking.

    Page-level titles (size >= 20) carry the active-section accent: a
    2px #ffe600 underline, one accent system for the whole UI.
    """
    lbl = QLabel(text.upper())
    accent = (f" border-bottom: 2px solid {T.COLOR_YELLOW};"
              if size >= 20 else "")
    lbl.setStyleSheet(
        f"color: {color or T.COLOR_TEXT_BRIGHT}; "
        f"font-family: 'Segoe UI Light','Segoe UI'; "
        f"font-size: {size}px; font-weight: 25; letter-spacing: 2px; "
        f"font-kerning: normal;{accent}")
    return lbl


def body(text: str, dim: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {T.COLOR_TEXT_DIM if dim else T.COLOR_TEXT_BODY}; font-size: 12px;")
    return lbl
