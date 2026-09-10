#!/usr/bin/env python3
"""GTA Bridge Launcher — unified PyQt5 front-end.

One app wrapping all distilled functionality:
  PLAY      - game select + launch + live bridge overlay (pools/memory)
  LIMITS    - limit adjuster categories/presets (SAS87 synthwave theme)
  MODS      - GGMM-style DLC/mod manager (install/uninstall/backup/restore,
              rw_inspect content stats, ariane.exe preview)
  INSTALLER - SAS 1987 wizard (recycled verbatim from _SAS_1987/87_installer)

Run:            venv64/Scripts/python.exe app.py
Build x64 exe:  venv64/Scripts/pyinstaller app.spec
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve, QSize, QUrl
from PyQt5.QtGui import QFont, QColor, QPainter, QLinearGradient, QPixmap, QImage, QIcon, QDesktopServices
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QStackedWidget, QListWidget, QListWidgetItem,
    QLineEdit, QComboBox, QFileDialog, QScrollArea, QFrame, QCheckBox,
    QAbstractItemView,
    QProgressBar, QTextEdit, QMessageBox, QSizePolicy, QSpinBox, QGroupBox,
    QDialog, QInputDialog, QMenuBar, QMenu, QProgressDialog, QPlainTextEdit,
)

# --- backend imports (toolkit-agnostic) -------------------------------------
from launcher import GTALauncher, DatabaseManager  # tkinter import is guarded there
from bridge_client import BridgeMonitor
import limit_adjuster_settings as LAS
from managers import txdlite
from managers import mapdata

KNOWN_EXES = {
    'gta_sa.exe': 'gtasa',
    'gta_vc.exe': 'gtavc',
    'gta-vc.exe': 'gtavc',
    'gta3.exe': 'gta3',
    'manhunt.exe': 'manhunt',
}

# NOTE: installer_src.ui.theme registers fonts at import time and MUST be
# imported after a QApplication exists -> wizard is imported lazily in
# InstallerScreen._launch(). Palette mirrored here for pre-QApp UI building.

from theme import (
    T, app_qss, NavButton, ActionButton, heading, body,
    _resolve_display_font,
)


def F(name: str) -> Path:
    """Frozen-aware resource path."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / name  # noqa: SLF001
    return HERE / name


def _data_dir() -> Path:
    """Writable launcher_data dir: next to the exe when frozen, repo dir in dev."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'launcher_data'
    return HERE / 'launcher_data'


def _open_archives_folder():
    """Open the archives folder in Explorer."""
    target = _data_dir() / 'dlc_presets' / 'archives'
    try:
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(str(target))
    except Exception:
        pass




class ScreenBase(QWidget):
    """Panel with the standard dark-green content background."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {T.COLOR_PANEL_BG};")
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(26, 20, 26, 20)
        self.root.setSpacing(12)


# =============================================================================
# PLAY screen
# =============================================================================

class OverlayWindow(QWidget):
    """Borderless always-on-top bridge stats overlay (replaces tk Toplevel)."""

    def __init__(self, game_dir: str):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool)
        self.setWindowTitle('GTA Bridge')
        self.setGeometry(20, 20, 350, 140)
        self.setStyleSheet(f"background: {T.COLOR_PANEL_BG}; "
                           f"border: 1px solid {T.COLOR_GROVE_GREEN};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        self.title = heading('GTA BRIDGE', 14)
        self.stats = body('waiting for game...')
        self.bridge = body('BRIDGE: connecting...')
        lay.addWidget(self.title)
        lay.addWidget(self.stats)
        lay.addWidget(self.bridge)

    def set_stats(self, line: str):
        self.stats.setText(line)

    def set_bridge(self, line: str, connected: bool):
        self.bridge.setText(line)
        self.bridge.setStyleSheet(
            f"color: {T.COLOR_SUCCESS if connected else T.COLOR_DANGER}; font-size: 12px;")


class BridgeWorker(QThread):
    stats = pyqtSignal(dict)

    def __init__(self, launcher: GTALauncher):
        super().__init__()
        self.launcher = launcher
        self.monitor = None

    def run(self):
        self.monitor = BridgeMonitor(callback=self.stats.emit)
        self.monitor.start()
        loop = QThread.eventLoop if False else None  # noqa: F841
        self.monitor.join()  # runs until stop_event set

    def stop(self):
        if self.monitor:
            self.monitor.stop()


# Pack groups whose members clash — enabling one greys out its siblings.
CONFLICT_GROUPS = {
    'vegetation': ['de_vegetation_by_sa_the_modder',
                   'improved_and_fixed_original_vegetation',
                   'mobile_vegetation'],
    'model_fixes': ['proper_models', 'd_org_patch_sa'],
    'map': ['parallax', 'ps2_map_+_fixes'],
}


class _PreviewCanvas(QWidget):
    """Center-left game preview render frame (pure paint placeholder).

    Checkerboard bed + hairline frame, kept square via heightForWidth.
    No timers, no IO -- a static stage for a future real render feed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def heightForWidth(self, w: int) -> int:
        return min(max(w, 240), 420)

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        tile = QPixmap(24, 24)
        tile.fill(QColor(T.COLOR_RAISED))
        tp = QPainter(tile)
        tp.fillRect(0, 0, 12, 12, QColor(T.COLOR_CHECKER))
        tp.fillRect(12, 12, 12, 12, QColor(T.COLOR_CHECKER))
        tp.end()
        p.drawTiledPixmap(r, tile)
        p.setPen(QColor(T.COLOR_BORDER))
        p.drawRect(r.adjusted(0, 0, -1, -1))
        p.setPen(QColor(T.COLOR_TEXT_DIM))
        p.setFont(QFont('Segoe UI', 9))
        p.drawText(r, Qt.AlignCenter, 'GAME PREVIEW RENDER')
        p.end()


class PlayScreen(ScreenBase):
    launch_requested = pyqtSignal()

    def __init__(self, launcher: GTALauncher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.overlay: OverlayWindow | None = None
        self.worker: BridgeWorker | None = None

        self.root.addWidget(heading('GAME SELECTION', 24))

        # ---- profile selector (legacy+ / test / user-added) ----
        prof_row = QHBoxLayout()
        prof_row.addWidget(body('PROFILE', dim=True))
        self.profile_combo = QComboBox()
        self.profile_combo.setStyleSheet(
            f"background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BRIGHT};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; padding:4px;")
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        prof_row.addWidget(self.profile_combo, 1)
        add_prof = ActionButton('+', accent=T.COLOR_WALKMAN_GREEN)
        add_prof.setFixedWidth(40)
        add_prof.setToolTip('Add current skygfx.ini / gta_bridge.ini as a new profile')
        add_prof.clicked.connect(self._add_current_profile)
        prof_row.addWidget(add_prof)
        self.root.addLayout(prof_row)
        self._refresh_profiles()

        cols = QHBoxLayout()
        left = QVBoxLayout()

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        form.addWidget(body('Game'), 0, 0)
        self.game_combo = QComboBox()
        self.game_combo.addItems(['gtasa'])
        self.game_combo.setStyleSheet(T.COMBO_QSS if hasattr(T, 'COMBO_QSS') else '')
        form.addWidget(self.game_combo, 0, 1)

        form.addWidget(body('Executable'), 1, 0)
        self.exe_edit = QLineEdit(launcher.get_last_exe_path() or 'gta_sa.exe')
        self.exe_edit.setStyleSheet(
            f"background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BRIGHT};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; padding:6px;")
        form.addWidget(self.exe_edit, 1, 1)
        browse = ActionButton('BROWSE')
        browse.clicked.connect(self._browse_exe)
        form.addWidget(browse, 1, 2)

        self.path_lbl = body(f'Path: {launcher.game_path}')
        form.addWidget(self.path_lbl, 2, 0, 1, 3)

        form.addWidget(body('Game Dir'), 3, 0)
        self.gamedir_edit = QLineEdit(
            launcher.config_manager.get_game_path('gtasa') or str(launcher.game_path))
        self.gamedir_edit.setStyleSheet(
            f"background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BRIGHT};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; padding:6px;")
        form.addWidget(self.gamedir_edit, 3, 1)
        browse_dir = ActionButton('BROWSE')
        browse_dir.clicked.connect(self._browse_game_dir)
        form.addWidget(browse_dir, 3, 2)
        self.detect_lbl = body('')
        form.addWidget(self.detect_lbl, 4, 0, 1, 3)
        self.preflight_lbl = body('')
        self.preflight_lbl.setStyleSheet(
            f"color:{T.COLOR_TEXT_DIM};font-size:10px;padding:0;")
        form.addWidget(self.preflight_lbl, 5, 0, 1, 3)
        left.addLayout(form)

        # ---- SESSION LOG block: sits directly under the Game Dir row -------
        live_row = QHBoxLayout()
        live_head = heading('LIVE', 12, T.COLOR_WALKMAN_GREEN)
        live_head.setStyleSheet(
            f"color:{T.COLOR_WALKMAN_GREEN}; font-size:11px; letter-spacing:1px;")
        live_row.addWidget(live_head)
        live_row.addStretch(1)
        log_uri = Path('E:/games/gtasa_skygfx_plus/gta_bridge_session.log').as_uri()
        open_log = QLabel(
            f'<a href="{log_uri}" style="color:{T.COLOR_LINK};'
            f'text-decoration:none;">open session log \u2197</a>')
        open_log.setCursor(Qt.PointingHandCursor)
        open_log.setOpenExternalLinks(True)
        live_row.addWidget(open_log)
        left.addLayout(live_row)
        self.live_log = QPlainTextEdit()
        self.live_log.setReadOnly(True)
        self.live_log.setFixedHeight(90)
        self.live_log.setPlainText(
            'SESSION LOG\n'
            'E:/games/gtasa_skygfx_plus/\n'
            '  gta_bridge_session.log\n'
            '\n'
            'waiting for first launch...\n'
            'bridge overlay stats echo here')
        self.live_log.setStyleSheet(
            f"QPlainTextEdit{{background:{T.COLOR_RAISED}; color:{T.COLOR_TEXT_DIM};"
            f"border:1px solid {T.COLOR_BORDER};"
            f"border-left:3px solid {T.COLOR_WALKMAN_GREEN}; border-radius:2px;"
            f"font-family:Consolas,'Courier New',monospace; font-size:10px;"
            f"padding:6px;}}")
        left.addWidget(self.live_log)

        # ---- PLAY row: left-aligned directly under the session log ---------
        play_row = QHBoxLayout()
        self.play_btn = ActionButton('\u25b6  PLAY', accent=T.COLOR_YELLOW)
        self.play_btn.setMinimumSize(180, 52)
        self.play_btn.clicked.connect(self._play)
        play_row.addWidget(self.play_btn)
        play_row.addStretch(1)
        left.addLayout(play_row)
        left.addStretch(1)
        cols.addLayout(left, 4)

        # ---- center: big square game preview render canvas ------------------
        center = QVBoxLayout()
        self.preview_canvas = _PreviewCanvas()
        center.addWidget(self.preview_canvas)
        center.addStretch(1)
        cols.addLayout(center, 4)

        # ---- right rail: DLC select (fills most) + compact PREVIEW tile -----
        right = QVBoxLayout()
        qm_box = QGroupBox('DLC')
        qm_box.setStyleSheet(
            f"QGroupBox{{color:{T.COLOR_TEXT_BRIGHT}; border:1px solid"
            f" {T.COLOR_WALKMAN_ORANGE}; border-radius:3px; margin-top:10px;"
            f" padding-top:6px; font-size:12px;}}")
        qv = QVBoxLayout(qm_box)
        qm_scroll = QScrollArea()
        qm_scroll.setWidgetResizable(True)
        qm_scroll.setStyleSheet('QScrollArea{border:none;background:transparent;}')
        qm_inner = QWidget()
        qm_inner.setStyleSheet('background: transparent;')
        self.qm_layout = QVBoxLayout(qm_inner)
        self.qm_layout.setContentsMargins(2, 2, 2, 2)
        self.qm_layout.setSpacing(4)
        qm_scroll.setWidget(qm_inner)
        qm_scroll.setMinimumWidth(300)
        qv.addWidget(qm_scroll)
        right.addWidget(qm_box, 1)

        prev_box = QGroupBox('PREVIEW')
        prev_box.setStyleSheet(
            f"QGroupBox{{color:{T.COLOR_WALKMAN_GREEN}; border:1px solid"
            f" {T.COLOR_DARK_GREEN}; border-radius:3px; margin-top:10px;"
            f" padding-top:6px; font-size:12px;}}")
        pv = QVBoxLayout(prev_box)
        game_title = QLabel('GTA SAN ANDREAS')
        game_title.setStyleSheet(
            f"color:{T.COLOR_TEXT_BRIGHT}; font-size:15px; font-weight:800;")
        pv.addWidget(game_title)
        self.preview_path = body(str(launcher.game_path))
        self.preview_path.setWordWrap(True)
        pv.addWidget(self.preview_path)
        self.preview_bridge = body('BRIDGE: idle')
        self.preview_bridge.setStyleSheet(f"color:{T.COLOR_TEXT_DIM};")
        pv.addWidget(self.preview_bridge)
        right.addWidget(prev_box)

        cols.addLayout(right, 3)
        self.root.addLayout(cols)
        self._build_quick_mods()

    # -- quick mods (GGMM-style one-click pack toggles + clash greying) ----
    def _pack_states(self) -> dict:
        states = dict(self.launcher.db_manager.get_dlc_state())
        idx = _data_dir() / 'dlc' / 'index.json'
        if idx.exists():
            try:
                raw = json.loads(idx.read_text(encoding='utf-8'))
                if isinstance(raw, dict):
                    raw = raw.get('packs', [])
                for p in raw if isinstance(raw, list) else []:
                    if isinstance(p, dict) and p.get('id'):
                        states.setdefault(p['id'], bool(p.get('default_enabled', True)))
            except (OSError, ValueError):
                pass
        return states

    def _conflict_with(self, pack_id: str, states: dict):
        for members in CONFLICT_GROUPS.values():
            if pack_id in members:
                for m in members:
                    if m != pack_id and states.get(m):
                        return m
        return None

    def _build_quick_mods(self):
        try:
            self._build_quick_mods_impl()
        except Exception:
            import traceback, logging
            logging.getLogger('bridge').error('DLC panel build failed:\n'+traceback.format_exc())
            try:
                self.qm_box.setTitle('DLC  [panel error - see log]')
            except Exception:
                pass

    def _build_quick_mods_impl(self):
        while self.qm_layout.count():
            it = self.qm_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        states = self._pack_states()
        names = {}
        src = self.launcher._dlc_source_dir()
        if src:
            idx = Path(src) / 'index.json'
            if idx.exists():
                try:
                    raw = json.loads(idx.read_text(encoding='utf-8'))
                    if isinstance(raw, dict):
                        raw = raw.get('packs', [])
                    for p in raw if isinstance(raw, list) else []:
                        if isinstance(p, dict) and p.get('id'):
                            names[p['id']] = p.get('name', p['id'])
                except (OSError, ValueError):
                    pass
        for pid in sorted(states):
            on = bool(states.get(pid))
            clash = self._conflict_with(pid, states)
            label = names.get(pid, pid)
            btn = QPushButton(f'[{"ON" if on else "OFF"}]  {label}')
            btn.pack_id = pid
            btn.setCursor(Qt.PointingHandCursor)
            if on:
                btn.setStyleSheet(
                    f"QPushButton{{text-align:left; padding:4px 8px;"
                    f"background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BRIGHT};"
                    f"border:1px solid {T.COLOR_WALKMAN_GREEN}; border-radius:2px;}}")
            else:
                btn.setStyleSheet(
                    f"QPushButton{{text-align:left; padding:4px 8px;"
                    f"background:transparent; color:{T.COLOR_TEXT_DIM};"
                    f"border:1px solid {T.COLOR_DARK_GREEN}; border-radius:2px;}}")
            if clash and not on:
                btn.setEnabled(False)
                btn.setToolTip(f'Clashes with {names.get(clash, clash)} — turn it off first.')
            else:
                btn.setToolTip('Click to toggle this pack (deploys on next launch).')
                btn.clicked.connect(lambda _, p=pid: self._toggle_pack(p))
            self.qm_layout.addWidget(btn)

        # --- DLC preset rows (pack_state engine) ---
        presets_dir = _data_dir() / 'dlc_presets'
        if presets_dir.is_dir():
            from managers.pack_state import load_presets, classify, install_available, PartState
            presets = load_presets(str(presets_dir))
            game_dir = str(self.launcher.game_path)
            # cap at 30 presets
            for preset in presets[:30]:
                pid = preset.get('id', '')
                title = preset.get('title', preset.get('name', pid))
                try:
                    ps = classify(preset, game_dir)
                except Exception:
                    continue
                row = QWidget()
                row.setStyleSheet('background: transparent;')
                rh = QHBoxLayout(row)
                rh.setContentsMargins(2, 1, 2, 1)
                rh.setSpacing(4)
                lbl = QLabel(title)
                lbl.setWordWrap(True)
                if ps.state == PartState.INSTALLED:
                    lbl.setStyleSheet(
                        f"color:{T.COLOR_TEXT_BRIGHT}; font-size:11px; padding:4px 8px;"
                        f"border:1px solid {T.COLOR_WALKMAN_ORANGE}; border-radius:2px;")
                    lbl.setToolTip('Installed — click to toggle')
                    lbl.mousePressEvent = lambda ev, p=pid: self._toggle_pack(p)
                elif ps.state == PartState.AVAILABLE:
                    lbl.setStyleSheet(
                        f"color:#c8b400; font-size:11px; padding:4px 8px;"
                        f"border:1px solid {T.COLOR_BORDER}; border-radius:2px;")
                    lbl.setToolTip('All parts available — select to install the DLC')
                    lbl.mousePressEvent = lambda ev, p=preset, g=game_dir: (
                        self._prompt_install_preset(p, g))
                else:  # MISSING
                    lbl.setStyleSheet(
                        f"color:#6a6152; font-size:11px; padding:4px 8px;"
                        f"border:1px solid {T.COLOR_BORDER}; border-radius:2px;")
                    lbl.setToolTip('Files missing — click for details')
                    lbl.mousePressEvent = lambda ev, p=preset: (
                        self._show_missing_parts(p))
                rh.addWidget(lbl, 1)
                self.qm_layout.addWidget(row)
        self.qm_layout.addStretch(1)

    def _prompt_install_preset(self, preset: dict, game_dir: str):
        """Show install confirmation dialog for an AVAILABLE preset."""
        title = preset.get('title', preset.get('name', preset.get('id', '?')))
        dlg = QDialog(self)
        dlg.setWindowTitle('Install DLC')
        dlg.setStyleSheet(f"background:{T.COLOR_BG};")
        dlg.setFixedSize(360, 140)
        lay = QVBoxLayout(dlg)
        msg = QLabel(f'Install files for {title} now?')
        msg.setStyleSheet(f"color:{T.COLOR_TEXT_BODY}; font-size:13px; padding:12px;")
        msg.setWordWrap(True)
        lay.addWidget(msg)
        self._install_status = QLabel('')
        self._install_status.setStyleSheet(
            f"color:{T.COLOR_TEXT_DIM}; font-size:11px; padding:4px 12px;")
        lay.addWidget(self._install_status)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        install_btn = QPushButton('INSTALL')
        install_btn.setStyleSheet(
            f"QPushButton{{background:{T.COLOR_WALKMAN_ORANGE}; color:{T.COLOR_ON_ACCENT};"
            f"border:none; border-radius:2px; padding:6px 18px; font-size:12px;}}"
            f"QPushButton:hover{{background:{T.COLOR_SUNSET_ORANGE};}}")
        later_btn = QPushButton('LATER')
        later_btn.setStyleSheet(
            f"QPushButton{{background:{T.COLOR_PANEL_BG}; color:{T.COLOR_TEXT_DIM};"
            f"border:1px solid {T.COLOR_BORDER}; border-radius:2px; padding:6px 18px;"
            f"font-size:12px;}}"
            f"QPushButton:hover{{background:{T.COLOR_HOVER_BG}; color:{T.COLOR_TEXT_BODY};}}")
        install_btn.clicked.connect(lambda: self._do_install_preset(preset, game_dir, dlg))
        later_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(install_btn)
        btn_row.addWidget(later_btn)
        lay.addLayout(btn_row)
        dlg.exec_()

    def _do_install_preset(self, preset: dict, game_dir: str, dlg: QDialog):
        """Run install_available with progress labels."""
        from managers.pack_state import install_available
        self._install_status.setText('Installing...')
        QApplication.processEvents()
        try:
            ok, lines = install_available(preset, game_dir)
            if ok:
                self._install_status.setText('INSTALLED & SELECTED')
                self.launcher.db_manager.set_dlc_enabled(preset['id'], True)
                QTimer.singleShot(300, dlg.accept)
                QTimer.singleShot(350, self._build_quick_mods)
            else:
                self._install_status.setText('Install failed — see log')
                QTimer.singleShot(2000, lambda: self._install_status.setText(''))
        except Exception as e:
            self._install_status.setText(f'Error: {e}')
            QTimer.singleShot(2000, lambda: self._install_status.setText(''))

    def _show_missing_parts(self, preset: dict):
        """Show missing parts dialog for a MISSING preset."""
        from managers.pack_state import classify, PartState
        game_dir = str(self.launcher.game_path)
        ps = classify(preset, game_dir)
        title = preset.get('title', preset.get('name', preset.get('id', '?')))
        dlg = QDialog(self)
        dlg.setWindowTitle(f'Missing files — {title}')
        dlg.setStyleSheet(f"background:{T.COLOR_BG};")
        dlg.setMinimumSize(480, 350)
        lay = QVBoxLayout(dlg)
        header = QLabel(f'Missing parts for {title}:')
        header.setStyleSheet(f"color:{T.COLOR_TEXT_BRIGHT}; font-size:13px; padding:8px;")
        lay.addWidget(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('QScrollArea{border:none;background:transparent;}')
        inner = QWidget()
        inner.setStyleSheet('background:transparent;')
        il = QVBoxLayout(inner)
        il.setSpacing(4)
        for pi in ps.missing_parts:
            part_row = QWidget()
            part_row.setStyleSheet('background:transparent;')
            prl = QHBoxLayout(part_row)
            prl.setContentsMargins(4, 2, 4, 2)
            prl.setSpacing(4)
            # find matching part spec for source_url
            part_spec = next((p for p in (preset.get('parts') or []) if p.get('name') == pi.name), {})
            src_url = part_spec.get('source_url', '') or ''
            info = QLabel(
                f"{pi.name}\n"
                f"  place: {pi.dest_rel}")
            info.setStyleSheet(
                f"color:{T.COLOR_TEXT_DIM}; font-size:11px; padding:4px 8px;"
                f"border:1px solid {T.COLOR_BORDER}; border-radius:2px;")
            info.setWordWrap(True)
            prl.addWidget(info, 1)
            if src_url:
                page_btn = QPushButton('OPEN PAGE')
                page_btn.setFlat(True)
                page_btn.setCursor(Qt.PointingHandCursor)
                page_btn.setStyleSheet(
                    f"QPushButton{{color:{T.COLOR_WALKMAN_GREEN}; font-size:10px;"
                    f"border:1px solid {T.COLOR_WALKMAN_GREEN}; border-radius:2px;"
                    f"padding:2px 8px; background:transparent;}}"
                    f"QPushButton:hover{{background:{T.COLOR_HOVER_BG};}}")
                page_btn.clicked.connect(
                    lambda _, u=src_url: QDesktopServices.openUrl(QUrl(u)))
                prl.addWidget(page_btn)
            il.addWidget(part_row)
        il.addStretch(1)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        btn_row = QHBoxLayout()
        archives_btn = QPushButton('ARCHIVES FOLDER')
        archives_btn.setStyleSheet(
            f"QPushButton{{background:{T.COLOR_PANEL_BG}; color:{T.COLOR_TEXT_DIM};"
            f"border:1px solid {T.COLOR_BORDER}; border-radius:2px; padding:6px 18px;"
            f"font-size:11px;}}"
            f"QPushButton:hover{{background:{T.COLOR_HOVER_BG}; color:{T.COLOR_TEXT_BODY};}}")
        archives_btn.clicked.connect(
            lambda: _open_archives_folder())
        btn_row.addWidget(archives_btn)
        close_btn = QPushButton('CLOSE')
        close_btn.setStyleSheet(
            f"QPushButton{{background:{T.COLOR_PANEL_BG}; color:{T.COLOR_TEXT_BODY};"
            f"border:1px solid {T.COLOR_BORDER}; border-radius:2px; padding:6px 18px;}}"
            f"QPushButton:hover{{background:{T.COLOR_HOVER_BG};}}")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)
        dlg.exec_()

    def _toggle_pack(self, pid: str):
        states = self._pack_states()
        cur = bool(states.get(pid))
        if not cur:
            # mutual exclusion: enabling a pack disables its clash siblings
            for members in CONFLICT_GROUPS.values():
                if pid in members:
                    for m in members:
                        if m != pid and states.get(m):
                            self.launcher.db_manager.set_dlc_enabled(m, False)
        self.launcher.db_manager.set_dlc_enabled(pid, not cur)
        self.deploy_worker = DeployWorker(self.launcher)
        self.deploy_worker.start()
        QTimer.singleShot(400, self._build_quick_mods)

    # -- profile selector (PyQt5 port of the launcher.py tkinter dropdown) --
    def _refresh_profiles(self):
        self.launcher.ensure_profiles()
        profs = self.launcher.profile_manager.list_profiles()
        if not profs:
            profs = ['legacy+', 'test']
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(profs)
        active = self.launcher.profile_manager.get_active_profile(self.launcher.game_path)
        if active in profs:
            self.profile_combo.setCurrentText(active)
        self.profile_combo.blockSignals(False)

    def _on_profile_selected(self, name: str):
        if not name:
            return
        try:
            self.launcher.select_profile(name)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, 'Profile error', str(e))

    def _add_current_profile(self):
        name, ok = QInputDialog.getText(self, 'New profile', 'Profile name:')
        if not ok or not name.strip():
            return
        name = name.strip()
        data = self.launcher.profile_manager.capture_current_config(self.launcher.game_path)
        if not data['skygfx'] and not data['bridge']:
            QMessageBox.warning(self, 'No config',
                                'Could not read current skygfx.ini / gta_bridge.ini')
            return
        self.launcher.profile_manager.save_profile(name, data)
        self.launcher.profile_manager.set_active_profile(self.launcher.game_path, name)
        self._refresh_profiles()
        self.profile_combo.setCurrentText(name)

    def _browse_exe(self):
        start = str(Path(self.launcher.game_path))
        fn, _ = QFileDialog.getOpenFileName(self, 'Select game executable', start,
                                            'Executables (*.exe)')
        if fn:
            self.exe_edit.setText(fn)
            self.launcher.set_selected_exe(fn)
            self.path_lbl.setText(f'Path: {Path(fn).parent}')

    def _browse_game_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, 'Select game folder',
            self.gamedir_edit.text().strip() or str(Path(self.launcher.game_path)))
        if not d:
            return
        exes = [f.name.lower() for f in Path(d).iterdir()
                if f.name.lower() in KNOWN_EXES]
        if not exes:
            self.detect_lbl.setText('NO GAME EXE FOUND')
            self.detect_lbl.setStyleSheet(f'color:{T.COLOR_DANGER};')
            return
        gid = KNOWN_EXES[exes[0]]
        try:
            self.launcher.config_manager.set_game_path(gid, d)
            ok = True
        except Exception:
            ok = False
        if ok:
            self.launcher.game_path = Path(d)
            self.gamedir_edit.setText(d)
            self.detect_lbl.setText('DETECTED: %s (%s)' % (gid, exes[0]))
            self.detect_lbl.setStyleSheet('')
            if hasattr(self, 'path_lbl'):
                self.path_lbl.setText('Path: %s' % d)
            self._run_preflight()
        else:
            self.detect_lbl.setText('SAVE FAILED')
            self.detect_lbl.setStyleSheet(f'color:{T.COLOR_DANGER};')

    def _play(self):
        exe = self.exe_edit.text().strip()
        if exe and Path(exe).exists():
            self.launcher.set_selected_exe(exe)
        self._run_preflight()
        try:
            self.launcher.launch_game()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, 'Launch failed', str(e))
            return
        if not self.overlay:
            self.overlay = OverlayWindow(self.launcher.game_path)
        self.overlay.show()
        if not self.worker:
            self.worker = BridgeWorker(self.launcher)
            self.worker.stats.connect(self._on_stats)
            self.worker.start()

    def _on_stats(self, d: dict):
        if hasattr(self, 'preview_bridge'):
            if d.get('connected'):
                self.preview_bridge.setText('BRIDGE: connected')
                self.preview_bridge.setStyleSheet(f"color:{T.COLOR_TEXT_BRIGHT};")
            else:
                self.preview_bridge.setText('BRIDGE: disconnected')
                self.preview_bridge.setStyleSheet(f"color:{T.COLOR_SUNSET_ORANGE};")
        if not self.overlay:
            return
        if d.get('connected'):
            mem_a = d.get('mem_avail'); mem_u = d.get('mem_used')
            pools = d.get('pools') or {}
            parts = []
            if mem_u is not None:
                parts.append(f'MEM: {mem_u}/{mem_a} MB')
            for name, um in pools.items():
                u, m = um
                parts.append(f'{name}: {u}/{m}')
            self.overlay.set_stats(' | '.join(parts) or 'game running')
            self.overlay.set_bridge('BRIDGE: connected', True)
        else:
            self.overlay.set_bridge('BRIDGE: disconnected', False)

    # ---- preflight hook (config registry sanity check) --------------------
    def _run_preflight(self):
        """Call config_registry.preflight and show result in preflight_lbl."""
        try:
            from managers import config_registry
            game_dir = str(self.launcher.game_path)
            ok, problems = config_registry.preflight(game_dir)
            if ok:
                self.preflight_lbl.setText('Config preflight: OK')
                self.preflight_lbl.setStyleSheet(
                    f'color:{T.COLOR_SUCCESS};font-size:10px;padding:0;')
            else:
                short = problems[:3]
                text = 'Config: ' + '; '.join(short)
                if len(problems) > 3:
                    text += f' (+{len(problems)-3} more)'
                self.preflight_lbl.setText(text)
                self.preflight_lbl.setStyleSheet(
                    f'color:#ff5533;font-size:10px;padding:0;')
        except Exception as e:
            self.preflight_lbl.setText(f'Preflight error: {e}')
            self.preflight_lbl.setStyleSheet(
                f'color:{T.COLOR_SUNSET_ORANGE};font-size:10px;padding:0;')


# =============================================================================
# LIMITS screen
# =============================================================================

class LimitsScreen(ScreenBase):
    def __init__(self, launcher: GTALauncher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.vars: dict[str, object] = {}

        self.root.addWidget(heading('LIMIT ADJUSTER', 24))

        # Crysis-style roll-out preset menu (slides downward, scrollable)
        self.preset_btn = ActionButton('PRESETS  \u25be', accent=T.COLOR_WALKMAN_GREEN)
        self.preset_btn.setFixedWidth(360)
        self.preset_btn.clicked.connect(self._toggle_preset_menu)
        self.root.addWidget(self.preset_btn, 0, Qt.AlignLeft)

        self.preset_menu = QScrollArea()
        self.preset_menu.setWidgetResizable(True)
        self.preset_menu.setFixedWidth(360)
        self.preset_menu.setMaximumHeight(0)
        self.preset_menu.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preset_menu.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.preset_menu.setStyleSheet(
            f"QScrollArea{{border:1px solid {T.COLOR_DARK_GREEN};"
            f"background:{T.COLOR_PANEL_BG};}}"
            f"QScrollBar:vertical{{width:8px;background:{T.COLOR_PANEL_BG};}}"
            f"QScrollBar::handle:vertical{{background:{T.COLOR_WALKMAN_ORANGE};"
            f"min-height:30px;border-radius:2px;}}")
        menu_inner = QWidget()
        menu_inner.setStyleSheet(f"background:{T.COLOR_PANEL_BG};")
        menu_lay = QVBoxLayout(menu_inner)
        menu_lay.setContentsMargins(4, 4, 4, 4)
        menu_lay.setSpacing(2)
        for name in LAS.LimitAdjusterSettings.PRESETS:
            mb = QPushButton(name)
            mb.setCursor(Qt.PointingHandCursor)
            mb.setStyleSheet(
                f"QPushButton{{color:{T.COLOR_TEXT_BODY};text-align:left;"
                f"padding:6px 10px;border:none;background:transparent;font-size:12px;}}"
                f"QPushButton:hover{{background:{T.COLOR_WALKMAN_GREEN};"
                f"color:{T.COLOR_ON_ACCENT};}}")
            mb.clicked.connect(lambda _, n=name: self._pick_preset(n))
            menu_lay.addWidget(mb)
        menu_lay.addStretch(1)
        self.preset_menu.setWidget(menu_inner)
        self.preset_menu_anim = QPropertyAnimation(self.preset_menu, b'maximumHeight')
        self.preset_menu_anim.setDuration(180)
        self.preset_menu_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.root.addWidget(self.preset_menu)

        self.status_lbl = body('')
        self.root.addWidget(self.status_lbl)

        # GTA V settings layout: category list left, setting rows right
        mid = QHBoxLayout()
        mid.setSpacing(10)
        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        self.cat_list = QListWidget()
        self.cat_list.setFixedWidth(230)
        self.cat_list.setStyleSheet(
            f"QListWidget{{background:{T.COLOR_PANEL_BG};color:{T.COLOR_TEXT_BODY};"
            f"border:1px solid {T.COLOR_DARK_GREEN};font-size:13px;outline:none;}}"
            f"QListWidget::item{{padding:8px 12px;}}"
            f"QListWidget::item:selected{{background:{T.COLOR_WALKMAN_ORANGE};"
            f"color:{T.COLOR_ON_ACCENT};}}"
            f"QListWidget::item:hover{{background:{T.COLOR_PANEL_BG_LIGHT};}}")
        left_col.addWidget(self.cat_list, 1)
        # RESET TO DEFAULTS row (two-step inline confirmation)
        reset_row = QHBoxLayout()
        reset_row.setContentsMargins(0, 0, 0, 0)
        self.reset_btn = QPushButton('RESET TO DEFAULTS')
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setStyleSheet(
            f"QPushButton{{background:{T.COLOR_PANEL_BG_LIGHT};"
            f"color:{T.COLOR_TEXT_DIM};"
            f"border:1px solid {T.COLOR_BORDER};border-radius:2px;"
            f"padding:6px 10px;font-size:11px;}}"
            f"QPushButton:hover{{border-color:{T.COLOR_SUNSET_ORANGE};"
            f"color:{T.COLOR_SUNSET_ORANGE};}}")
        self.reset_btn.clicked.connect(self._reset_defaults)
        reset_row.addWidget(self.reset_btn)
        self.reset_lbl = QLabel('')
        self.reset_lbl.setStyleSheet(
            f"color:{T.COLOR_TEXT_DIM};font-size:10px;padding:2px 4px;")
        reset_row.addWidget(self.reset_lbl, 1)
        left_col.addLayout(reset_row)
        self._reset_armed = False
        self._reset_timer = QTimer()
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(self._reset_disarm)
        mid.addLayout(left_col)
        self.rows_scroll = QScrollArea()
        self.rows_scroll.setWidgetResizable(True)
        self.rows_scroll.setStyleSheet(
            f"QScrollArea{{border:1px solid {T.COLOR_DARK_GREEN};"
            f"background:{T.COLOR_PANEL_BG};}}"
            f"QScrollBar:vertical{{width:8px;background:{T.COLOR_PANEL_BG};}}"
            f"QScrollBar::handle:vertical{{background:{T.COLOR_WALKMAN_ORANGE};"
            f"min-height:30px;border-radius:2px;}}")
        self.rows_inner = QWidget()
        self.rows_inner.setStyleSheet(f"background:{T.COLOR_PANEL_BG};")
        self.rows_lay = QVBoxLayout(self.rows_inner)
        self.rows_lay.setContentsMargins(10, 8, 10, 8)
        self.rows_lay.setSpacing(2)
        self.rows_lay.addStretch(1)
        self.rows_scroll.setWidget(self.rows_inner)
        mid.addWidget(self.rows_scroll, 1)
        self.root.addLayout(mid, 1)

        # GTA V bottom description bar
        self.desc_bar = QLabel('Hover a setting to see what it does.')
        self.desc_bar.setFixedHeight(44)
        self.desc_bar.setWordWrap(True)
        self.desc_bar.setStyleSheet(            f"background:{T.COLOR_PANEL_BG_LIGHT};color:{T.COLOR_TEXT_DIM};"
            f"border:1px solid {T.COLOR_DARK_GREEN};padding:6px 10px;font-size:12px;")
        self.root.addWidget(self.desc_bar)

        # render-distance slider (controls bridge max_lod_scale 1.0-6.0)
        from PyQt5.QtWidgets import QSlider
        rd_row = QHBoxLayout()
        rd_lbl = QLabel('RENDER DISTANCE')
        rd_lbl.setStyleSheet(f"color:{T.COLOR_TEXT_BODY};font-size:11px;")
        rd_lbl.setMinimumWidth(140)
        rd_lbl.setToolTip(
            'Dynamic LOD draw-distance scale. The bridge ASI scales this live by pool '
            'headroom (1.2x at full pools up to this max when pools are free). '
            'Higher = farther LODs, needs free pool capacity.')
        self.rd_slider = QSlider(Qt.Horizontal)
        self.rd_slider.setRange(10, 60)  # 1.0 - 6.0
        try:
            cur = float(self.launcher.db_manager.get_limit('gtasa', 'max_lod_scale') or 4.0)
        except (TypeError, ValueError):
            cur = 4.0
        self.rd_slider.setValue(int(min(6.0, max(1.0, cur)) * 10))
        self.rd_val = QLabel(f'{self.rd_slider.value() / 10:.1f}x')
        self.rd_val.setStyleSheet(f"color:{T.COLOR_TEXT_BRIGHT};font-size:12px;min-width:36px;")
        self.rd_slider.valueChanged.connect(self._on_render_distance)
        rd_row.addWidget(rd_lbl)
        rd_row.addWidget(self.rd_slider, 1)
        rd_row.addWidget(self.rd_val)
        self.root.addLayout(rd_row)

        apply_row = QHBoxLayout()
        apply_row.addStretch(1)
        ap = ActionButton('APPLY + WRITE INI', accent=T.COLOR_SUNSET_ORANGE)
        ap.clicked.connect(self._apply_all)
        apply_row.addWidget(ap)
        self.root.addLayout(apply_row)

        # populate category list + rows
        self._cat_entries: dict[str, list] = {}
        for cat, catdef in LAS.LimitAdjusterSettings.LIMIT_CATEGORIES.items():
            entries = catdef.get('settings', []) if isinstance(catdef, dict) else catdef
            self._cat_entries[cat] = entries
            self.cat_list.addItem(cat)
        self.cat_list.currentRowChanged.connect(self._show_category)
        self.cat_list.setCurrentRow(0)

    LIMIT_RELATIONS = {
        'Peds': 'PedIntelligence, PtrNodeSingle/Double, EntryInfoNode, MemoryAvailable',
        'Vehicles': 'VehicleModels, VehicleStructs, PtrNodeDouble, EntryInfoNode, MemoryAvailable',
        'Buildings': 'AlphaEntityList, VisibleEntityPtrs, PtrNodeDouble, MemoryAvailable',
        'Objects': 'Dummys, AtomicModels, TimeModels, PtrNodeSingle, MemoryAvailable',
        'AtomicModels': 'TxdStore, MemoryAvailable',
        'DamageAtomicModels': 'TxdStore, MemoryAvailable',
        'TimeModels': 'TxdStore, MemoryAvailable',
        'ClumpModels': 'TxdStore, MemoryAvailable',
        'VehicleModels': 'TxdStore, MemoryAvailable',
        'PedModels': 'TxdStore, MemoryAvailable',
        'WeaponModels': 'TxdStore, MemoryAvailable',
        'StreamingInfo': 'MemoryAvailable, ExtraObjectsDir',
        'MemoryAvailable': 'EVERYTHING — this is the master memory budget; raise it first when pushing pools up',
        'VRAM': 'MemoryAvailable (rule of thumb: RAM/4, e.g. 32GB RAM -> 8GB VRAM budget)',
        'TxdStore': 'MemoryAvailable',
        'PtrNodeSingle': 'Pools that store pointers (Objects, Buildings, coronas...)',
        'PtrNodeDouble': 'Pools with double links (Vehicles, Buildings...)',
        'EntryInfoNode': 'Peds, Vehicles, Buildings (visibility/collision lists)',
        'PedIntelligence': 'Peds',
        'Dummys': 'Objects',
        'AlphaEntityList': 'Buildings, VisibleEntityPtrs',
        'VisibleEntityPtrs': 'Buildings, AlphaEntityList',
        'VehicleStructs': 'Vehicles',
    }

    # ---- GTA V style helpers -------------------------------------------------
    def _toggle_preset_menu(self):
        target = 230 if self.preset_menu.maximumHeight() == 0 else 0
        self.preset_menu_anim.stop()
        self.preset_menu_anim.setStartValue(self.preset_menu.maximumHeight())
        self.preset_menu_anim.setEndValue(target)
        self.preset_menu_anim.start()

    def _pick_preset(self, name: str):
        self._toggle_preset_menu()
        self.apply_preset(name)

    def _show_category(self, row: int):
        if row < 0:
            return
        cat = self.cat_list.item(row).text()
        entries = self._cat_entries.get(cat, [])
        while self.rows_lay.count() > 1:  # keep trailing stretch
            item = self.rows_lay.takeAt(self.rows_lay.count() - 2)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for ent in entries:
            self.rows_lay.insertWidget(self.rows_lay.count() - 1,
                                       self._make_setting_row(ent))

    def _make_setting_row(self, ent: dict):
        row = QWidget()
        row.setStyleSheet('background: transparent;')
        h = QHBoxLayout(row)
        h.setContentsMargins(6, 3, 6, 3)
        h.setSpacing(10)
        tip = self._limit_tooltip(ent)
        row.limit_tip = tip
        nm = QLabel(ent['name'])
        nm.setStyleSheet(f"color: {T.COLOR_TEXT_BODY}; font-size: 12px;")
        nm.setMinimumWidth(200)
        nm.setToolTip(tip)
        h.addWidget(nm)
        h.addStretch(1)
        saved = self.launcher.db_manager.get_limit('gtasa', ent['name'])
        try:
            dflt = int(float(ent.get('default', 0)))
            is_int = True
        except (TypeError, ValueError):
            dflt = str(ent.get('default', ''))
            is_int = False
        if is_int:
            sp = QSpinBox()
            sp.setRange(0, int(float(ent.get('max', 999999)) or 999999))
            sp.setValue(dflt)
            sp.setMinimumWidth(130)
            sp.setAlignment(Qt.AlignRight)
            sp.setToolTip(tip)
            if saved is not None:
                try:
                    sp.setValue(int(float(saved)))
                except (TypeError, ValueError):
                    pass
            sp.valueChanged.connect(
                lambda val, n=ent['name']: self._on_change(n, val))
            widget = sp
        else:
            le = QLineEdit(str(saved if saved is not None else dflt))
            le.setMinimumWidth(130)
            le.setToolTip(tip)
            le.setStyleSheet(
                f"background:{T.COLOR_PANEL_BG}; color:{T.COLOR_TEXT_BRIGHT};"
                f"border:1px solid {T.COLOR_DARK_GREEN}; padding:3px;")
            le.textChanged.connect(
                lambda txt, n=ent['name']: self._on_change_text(n, txt))
            widget = le
        self.vars[ent['name']] = widget
        h.addWidget(widget)
        row.installEventFilter(self)
        return row

    def eventFilter(self, obj, event):
        if hasattr(obj, 'limit_tip'):
            from PyQt5.QtCore import QEvent
            if event.type() == QEvent.Enter:
                obj.setStyleSheet(
                    f"background:{T.COLOR_WALKMAN_GREEN};")
                self.desc_bar.setText(obj.limit_tip)
            elif event.type() == QEvent.Leave:
                obj.setStyleSheet('background: transparent;')
        return super().eventFilter(obj, event)

    def _on_render_distance(self, val: int):
        """Render-distance slider: store max_lod_scale (1.0-6.0) + rewrite bridge ini."""
        scale = val / 10.0
        self.rd_val.setText(f'{scale:.1f}x')
        try:
            self.launcher.db_manager.set_limit('gtasa', 'max_lod_scale', scale)
            self.launcher.write_bridge_ini()
            self.status_lbl.setText(f'Render distance scale {scale:.1f}x written to gta_bridge.ini')
        except Exception as e:
            self.status_lbl.setText(f'Slider write failed: {e}')

    def _on_change_text(self, name: str, txt: str):
        self.launcher.db_manager.set_limit('gtasa', name, txt, None)

    def _limit_tooltip(self, ent: dict) -> str:
        name = ent.get('name', '')
        desc = ent.get('description', '') or ''
        rel = self.LIMIT_RELATIONS.get(name)
        tip = f'{name}\n\n{desc}' if desc else name
        if rel:
            tip += f'\n\nScales with: {rel}'
        else:
            tip += ('\n\nScales with: MemoryAvailable / VRAM — raise the memory '
                    'budget alongside pool limits.')
        tip += f'\n\nDefault: {ent.get("default", "?")}   Max: {ent.get("max", "?")}'
        return tip

    def _on_change(self, name: str, val: int):
        self.launcher.db_manager.set_limit('gtasa', name, val, val)

    def apply_preset(self, name: str):
        vals = LAS.LimitAdjusterSettings.PRESETS.get(name, {})
        n = 0
        for key, val in vals.items():
            w = self.vars.get(key)
            if isinstance(w, QSpinBox):
                try:
                    w.setValue(int(float(val)))
                    n += 1
                except (TypeError, ValueError):
                    continue
            elif isinstance(w, QLineEdit):
                w.setText(str(val))
                n += 1
        self.status_lbl.setText(f'"{name}" loaded ({n} values). Press APPLY to persist.')

    def _apply_all(self):
        # GTA V layout: self.vars only holds the CURRENT category's widgets.
        # Write every limit: widget value when visible, else preserve db value.
        for cat, catdef in LAS.LIMIT_CATEGORIES.items():
            for ent in catdef.get('settings', []):
                name = ent['name']
                w = self.vars.get(name)
                if w is not None:
                    if isinstance(w, QSpinBox):
                        self.launcher.db_manager.set_limit('gtasa', name, w.value(), w.value())
                    elif isinstance(w, QLineEdit):
                        self.launcher.db_manager.set_limit('gtasa', name, w.text(), None)
                else:
                    saved = self.launcher.db_manager.get_limit('gtasa', name)
                    if saved is not None:
                        try:
                            self.launcher.db_manager.set_limit(
                                'gtasa', name, int(float(saved)), int(float(saved)))
                        except (TypeError, ValueError):
                            self.launcher.db_manager.set_limit('gtasa', name, str(saved), None)
        p = self.launcher.write_bridge_ini()
        self.status_lbl.setText(f'Saved. INI: {p}')

    # ---- RESET TO DEFAULTS (two-step inline confirm) -----------------------
    def _reset_defaults(self):
        if not self._reset_armed:
            self._reset_armed = True
            self.reset_btn.setText('CLICK AGAIN TO CONFIRM')
            self.reset_lbl.setText('')
            self._reset_timer.start(5000)
            return
        self._reset_timer.stop()
        self._reset_armed = False
        self.reset_btn.setText('RESET TO DEFAULTS')
        # perform reset for every registry key
        from managers import config_registry
        game_dir = str(self.launcher.game_path)
        ok_count = 0
        fail_list = []
        for key in config_registry.FILES:
            if config_registry.reset_to_defaults(key, game_dir):
                ok_count += 1
            else:
                fail_list.append(key)
        # re-read screen values from re-loaded files
        self._refresh_from_files()
        if fail_list:
            self.reset_lbl.setText(
                f'RESET OK ({ok_count} files), FAILED: {", ".join(fail_list)}')
            self.reset_lbl.setStyleSheet(
                f'color:{T.COLOR_SUNSET_ORANGE};font-size:10px;')
        else:
            self.reset_lbl.setText(f'RESET OK ({ok_count} files)')
            self.reset_lbl.setStyleSheet(
                f'color:{T.COLOR_SUCCESS};font-size:10px;')

    def _reset_disarm(self):
        self._reset_armed = False
        self.reset_btn.setText('RESET TO DEFAULTS')

    def _refresh_from_files(self):
        """Re-read current values from game files into the UI widgets."""
        from managers import config_registry
        game_dir = str(self.launcher.game_path)
        # re-read render distance from gta_bridge.ini
        cp = config_registry.read('gta_bridge', game_dir)
        if cp.has_section('BRIDGE'):
            try:
                lod = float(cp.get('BRIDGE', 'max_lod_scale'))
                self.rd_slider.setValue(int(min(6.0, max(1.0, lod)) * 10))
            except (TypeError, ValueError):
                pass
        # re-read limit adjuster values from db (they were written by reset)
        for cat, catdef in LAS.LIMIT_CATEGORIES.items():
            for ent in catdef.get('settings', []):
                name = ent['name']
                w = self.vars.get(name)
                if w is None:
                    continue
                saved = self.launcher.db_manager.get_limit('gtasa', name)
                if saved is None:
                    continue
                if isinstance(w, QSpinBox):
                    try:
                        w.setValue(int(float(saved)))
                    except (TypeError, ValueError):
                        pass
                elif isinstance(w, QLineEdit):
                    w.setText(str(saved))
        self.status_lbl.setText('Values refreshed from reset files.')


# =============================================================================
# MODS screen (GGMM style)
# =============================================================================

class DeployWorker(QThread):
    done = pyqtSignal(list)

    def __init__(self, launcher: GTALauncher):
        super().__init__()
        self.launcher = launcher

    def run(self):
        try:
            self.done.emit(self.launcher.deploy_dlc())
        except Exception as e:  # noqa: BLE001
            self.done.emit([('error', str(e))])


class TxdEditorDialog(QDialog):
    """GGMM-style TXD editor backed by managers.txdlite (pure-Python RW engine)."""

    def __init__(self, txd_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'TXD Editor — {Path(txd_path).name}')
        self.resize(760, 500)
        self.txd_path = str(txd_path)
        self.txd = txdlite.TxdFile.load(self.txd_path)

        lay = QVBoxLayout(self)
        split = QHBoxLayout()
        self.listw = QListWidget()
        self.preview = QLabel('select a texture')
        self.preview.setMinimumSize(256, 256)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(
            f"background:{T.COLOR_PANEL_BG_LIGHT}; border:1px solid {T.COLOR_DARK_GREEN};")
        split.addWidget(self.listw, 1)
        split.addWidget(self.preview, 1)
        lay.addLayout(split, 1)

        btns = QHBoxLayout()
        for label, slot in (('EXPORT PNG', self._export),
                            ('REPLACE FROM PNG', self._replace),
                            ('SAVE TXD', self._save)):
            b = ActionButton(label)
            b.clicked.connect(slot)
            btns.addWidget(b)
        lay.addLayout(btns)

        self.info = body('')
        lay.addWidget(self.info)

        for t in self.txd.textures:
            self.listw.addItem(QListWidgetItem(
                f"{t.name}   {t.width}x{t.height}  {t.fmt_name()}"))
        self.listw.currentRowChanged.connect(self._show)
        if self.listw.count():
            self.listw.setCurrentRow(0)

    def _cur(self):
        row = self.listw.currentRow()
        return self.txd.textures[row] if 0 <= row < len(self.txd.textures) else None

    def _show(self, _row: int):
        t = self._cur()
        if not t:
            return
        try:
            img = txdlite.decode_mip(t)
            img.thumbnail((256, 256))
            self._pix_buf = img.tobytes('raw', 'RGBA')
            qimg = QImage(self._pix_buf,
                          img.width, img.height, QImage.Format_RGBA8888)
            self.preview.setPixmap(QPixmap.fromImage(qimg))
            self.info.setText(
                f"{t.name}  {t.width}x{t.height}  {t.fmt_name()}  mips={t.num_levels}"
                f"{'  alpha' if t.flags & txdlite.FLAG_ALPHA else ''}")
        except Exception as e:
            self.preview.setText(f'decode failed:\n{e}')

    def _export(self):
        t = self._cur()
        if not t:
            return
        out, _ = QFileDialog.getSaveFileName(self, 'Export texture', f"{t.name}.png",
                                             'PNG (*.png)')
        if out:
            txdlite.decode_mip(t).save(out)
            self.info.setText(f'exported {t.name} -> {out}')

    def _replace(self):
        t = self._cur()
        if not t:
            return
        src, _ = QFileDialog.getOpenFileName(self, 'Replace from image', '',
                                             'Images (*.png *.jpg *.jpeg *.bmp)')
        if not src:
            return
        try:
            from PIL import Image
            self.txd.replace(t.name, Image.open(src))
            self._show(self.listw.currentRow())
            self.info.setText(f'replaced {t.name} — click SAVE TXD to write file')
        except Exception as e:
            QMessageBox.warning(self, 'Replace failed', str(e))

    def _save(self):
        out, _ = QFileDialog.getSaveFileName(self, 'Save TXD', self.txd_path,
                                             'TXD (*.txd)')
        if out:
            try:
                self.txd.save(out)
                self.info.setText(f'saved {out}')
            except Exception as e:
                QMessageBox.warning(self, 'Save failed', str(e))


class ModsScreen(ScreenBase):
    FILTERS = [('ALL', None), ('MODELS', {'models'}), ('SCRIPTS', {'scripting', 'diagnostics'}),
               ('DATA', {'data', 'fixes'}), ('GRAPHICS', {'graphics', 'effects'})]

    def __init__(self, launcher: GTALauncher, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.packs: list[dict] = []
        self.filter: str | None = None
        self.worker: DeployWorker | None = None

        top = QHBoxLayout()
        top.addWidget(heading('MOD MANAGER', 24))
        top.addStretch(1)
        rl = ActionButton('RELOAD')
        rl.clicked.connect(self.reload)
        top.addWidget(rl)
        self.root.addLayout(top)

        tabrow = QHBoxLayout()
        self.tab_files = ActionButton('FILES')
        self.tab_audit = ActionButton('AUDIT')
        for tb in (self.tab_files, self.tab_audit):
            tb.setCheckable(True)
        self.tab_files.setChecked(True)
        self.tab_files.clicked.connect(lambda: self._switch_modtab(0))
        self.tab_audit.clicked.connect(lambda: self._switch_modtab(1))
        tabrow.addWidget(self.tab_files)
        tabrow.addWidget(self.tab_audit)
        tabrow.addStretch(1)
        self.root.addLayout(tabrow)
        self.modstack = QStackedWidget()
        self.files_page = QWidget()
        self.files_layout = QVBoxLayout(self.files_page)
        self.files_layout.setContentsMargins(0, 0, 0, 0)

        mid = QHBoxLayout()
        # left column: action buttons + list
        left = QVBoxLayout()
        btns = QHBoxLayout()
        inst = ActionButton('INSTALL')
        inst.clicked.connect(lambda: self._set_enabled(True))
        uninst = ActionButton('UNINSTALL', danger=True)
        uninst.clicked.connect(self._uninstall_selected)
        backup = ActionButton('BACKUP LIST')
        backup.clicked.connect(self._toggle_backups_slide)
        restore = ActionButton('RESTORE ORIGINALS')
        restore.clicked.connect(self._restore_originals)
        scan = ActionButton('SCAN FOR ISSUES', accent=T.COLOR_LCS_AMBER)
        scan.clicked.connect(self._scan_txds)
        fixall = ActionButton('FIX ALL ISSUES', accent=T.COLOR_WALKMAN_GREEN)
        fixall.clicked.connect(self._fix_all_txds)
        flt = ActionButton('FILTERS')
        flt.clicked.connect(self._toggle_filter_slide)
        for b in (inst, uninst, backup, restore, scan, fixall, flt):
            btns.addWidget(b)
        left.addLayout(btns)
        inst.clicked.disconnect()
        inst.clicked.connect(self._toggle_install_slide)
        self.install_slide = QFrame()
        self.install_slide.setStyleSheet(
            f"QFrame {{ background:{T.COLOR_PANEL_BG_LIGHT};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; border-radius:2px; }}")
        _isl = QHBoxLayout(self.install_slide)
        _isl.setContentsMargins(6, 4, 6, 4)
        _isl.addWidget(body('install from:'))
        _zipb = ActionButton('FROM .ZIP')
        _zipb.clicked.connect(self._install_from_zip)
        _isl.addWidget(_zipb)
        _foldb = ActionButton('FROM FOLDER')
        _foldb.clicked.connect(self._install_from_folder)
        _isl.addWidget(_foldb)
        _isl.addStretch(1)
        self.install_slide.setMaximumHeight(0)
        self.install_slide.setVisible(False)
        self.install_anim = QPropertyAnimation(self.install_slide, b'maximumHeight')
        self.install_anim.setDuration(180)
        self.install_anim.setEasingCurve(QEasingCurve.OutCubic)
        left.addWidget(self.install_slide)
        self.filter_slide = QFrame()
        self.filter_slide.setStyleSheet(
            f"QFrame {{ background:{T.COLOR_PANEL_BG_LIGHT};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; border-radius:2px; }}")
        _fl = QHBoxLayout(self.filter_slide)
        _fl.setContentsMargins(6, 4, 6, 4)
        _fl.addWidget(body('issue types:'))
        self.ck_txd = QCheckBox('TXDs')
        self.ck_mip = QCheckBox('Mipmaps')
        self.ck_orph = QCheckBox('Orphaned refs')
        self.ck_raw = QCheckBox('Raw configs')
        for ck in (self.ck_txd, self.ck_mip, self.ck_orph, self.ck_raw):
            ck.setChecked(True)
            _fl.addWidget(ck)
        _fl.addStretch(1)
        self.filter_slide.setMaximumHeight(0)
        self.filter_slide.setVisible(False)
        self.filter_anim = QPropertyAnimation(self.filter_slide, b'maximumHeight')
        self.filter_anim.setDuration(180)
        self.filter_anim.setEasingCurve(QEasingCurve.OutCubic)
        left.addWidget(self.filter_slide)
        self.backups_slide = QFrame()
        self.backups_slide.setStyleSheet(
            f"QFrame {{ background:{T.COLOR_PANEL_BG_LIGHT};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; border-radius:2px; }}")
        _bs = QVBoxLayout(self.backups_slide)
        _bs.setContentsMargins(6, 4, 6, 4)
        _bsrow = QHBoxLayout()
        _bsrow.addWidget(body('backups:'))
        _openb = ActionButton('OPEN BACKUP FOLDER')
        _openb.clicked.connect(self._open_backup_folder)
        _bsrow.addWidget(_openb)
        _rob = ActionButton('RESTORE ORIGINALS')
        _rob.clicked.connect(self._restore_originals)
        _bsrow.addWidget(_rob)
        _bsrow.addStretch(1)
        _bs.addLayout(_bsrow)
        _bs.addWidget(body('uninstalled mods (restorable):'))
        self.uninst_listw = QListWidget()
        self.uninst_listw.setStyleSheet(
            f"QListWidget {{ background:{T.COLOR_PANEL_BG}; color:{T.COLOR_TEXT_BODY};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; font-size:11px; }}")
        _bs.addWidget(self.uninst_listw)
        _rrow = QHBoxLayout()
        _rrow.addStretch(1)
        _rsub = ActionButton('RESTORE SELECTED')
        _rsub.clicked.connect(self._restore_uninstalled)
        _rrow.addWidget(_rsub)
        _bs.addLayout(_rrow)
        self.backups_slide.setMaximumHeight(0)
        self.backups_slide.setVisible(False)
        self.backups_anim = QPropertyAnimation(self.backups_slide, b'maximumHeight')
        self.backups_anim.setDuration(180)
        self.backups_anim.setEasingCurve(QEasingCurve.OutCubic)
        left.addWidget(self.backups_slide)

        self.listw = QListWidget()
        self.listw.setStyleSheet(
            f"QListWidget {{ background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BODY};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; font-size:12px; }}"
            f"QListWidget::item:selected {{ background:{T.COLOR_GROVE_GREEN};"
            f" color:{T.COLOR_ON_ACCENT}; }}")
        self.listw.currentRowChanged.connect(self._show_details)
        left.addWidget(self.listw, 1)

        ml_head = heading('MOD LOADER FOLDERS', 13, T.COLOR_WALKMAN_GREEN)
        left.addWidget(ml_head)
        pack_row = QHBoxLayout()
        pack_row.addWidget(body('pack'))
        self.pack_combo = QComboBox()
        self.pack_combo.addItem(self._PACK_NONE)
        for p in self._load_presets():
            self.pack_combo.addItem(p.get('name', p.get('id')))
        self.pack_combo.currentTextChanged.connect(self._on_pack_selected)
        self.pack_combo.setStyleSheet(
            f"QComboBox {{ background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BODY};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; padding:2px 6px; }}")
        pack_row.addWidget(self.pack_combo, 1)
        left.addLayout(pack_row)
        self.ml_listw = QListWidget()
        self.ml_listw.setStyleSheet(
            f"QListWidget {{ background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BODY};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; font-size:12px; }}"
            f"QListWidget::item:selected {{ background:{T.COLOR_GROVE_GREEN};"
            f" color:{T.COLOR_ON_ACCENT}; }}")
        self.ml_listw.itemDoubleClicked.connect(self._toggle_modloader)
        self.ml_listw.setAcceptDrops(True)
        self.ml_listw.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.ml_listw.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ml_listw.customContextMenuRequested.connect(self._ml_context_menu)
        self.ml_listw.setDropIndicatorShown(True)
        self.ml_listw.dragEnterEvent = self._ml_drag_enter
        self.ml_listw.dragMoveEvent = lambda ev: ev.acceptProposedAction()
        self.ml_listw.dropEvent = self._ml_drop
        self.ml_listw.setToolTip('double-click = enable/disable · drag zip/folder '
                                 'here to install into modloader/')
        left.addWidget(self.ml_listw, 1)

        filt = QHBoxLayout()
        for label, cats in self.FILTERS:
            b = ActionButton(label)
            b.clicked.connect(lambda _, c=cats: self._filter(c))
            filt.addWidget(b)
        filt.addStretch(1)
        left.addLayout(filt)
        mid.addLayout(left, 5)

        # right column: details / preview
        right = QVBoxLayout()
        right.addWidget(heading('PREVIEW', 16, T.COLOR_WALKMAN_GREEN))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setStyleSheet(
            f"QTextEdit {{ background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BODY};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; font-family:Consolas; font-size:11px; }}")
        right.addWidget(self.details, 1)
        prev_row = QHBoxLayout()
        ari = ActionButton('OPEN IN ARIANE', accent=T.COLOR_LCS_AMBER)
        ari.clicked.connect(self._open_ariane)
        prev_row.addWidget(ari)
        etx = ActionButton('EDIT TXD', accent=T.COLOR_WALKMAN_GREEN)
        etx.clicked.connect(self._edit_txd)
        prev_row.addWidget(etx)
        prev_row.addStretch(1)
        right.addLayout(prev_row)
        mid.addLayout(right, 4)
        self.files_layout.addLayout(mid, 1)
        self.audit_page = QWidget()
        _audit_layout = QVBoxLayout(self.audit_page)
        _audit_layout.setContentsMargins(0, 0, 0, 0)
        self._inspector = InspectorScreen(self.launcher)
        _audit_layout.addWidget(self._inspector)
        self.modstack.addWidget(self.files_page)
        self.modstack.addWidget(self.audit_page)
        self.root.addWidget(self.modstack, 1)

        self.status = body('Ready.')
        self.root.addWidget(self.status)
        self.reload()

    def _switch_modtab(self, ix: int):
        self.tab_files.setChecked(ix == 0)
        self.tab_audit.setChecked(ix == 1)
        self.modstack.setCurrentIndex(ix)

    # -- data -----------------------------------------------------------------
    def reload(self):
        idx = _data_dir() / 'dlc' / 'index.json'
        packs: list[dict] = []
        if idx.exists():
            raw = json.loads(idx.read_text(encoding='utf-8'))
            packs = raw.get('packs', []) if isinstance(raw, dict) else raw
        states = self.launcher.db_manager.get_dlc_state()
        for p in packs:
            p['_enabled'] = states.get(p['id'], bool(p.get('default_enabled', True)))
        self.packs = sorted(packs, key=lambda p: (p.get('layer', 9), p.get('order', 99)))
        self._fill_list()
        self._fill_modloader()

    def _fill_list(self):
        self.listw.clear()
        for p in self.packs:
            if self.filter and p.get('category') not in self.filter:
                continue
            mark = '[ON] ' if p['_enabled'] else '[OFF]'
            sz = p.get('bytes') or 0
            item = QListWidgetItem(f"{mark} {p['name']}  ({sz/1024/1024:.1f} MB)")
            item.setData(Qt.UserRole, p['id'])
            self.listw.addItem(item)

    def _selected(self) -> dict | None:
        it = self.listw.currentItem()
        if not it:
            return None
        pid = it.data(Qt.UserRole)
        return next((p for p in self.packs if p['id'] == pid), None)

    # -- actions ---------------------------------------------------------------
    def _set_enabled(self, enabled: bool):
        p = self._selected()
        if not p:
            return
        self.launcher.db_manager.set_dlc_enabled(p['id'], enabled)
        self._deploy_async(f"{p['id']} -> {'enabled' if enabled else 'disabled'}")

    def _deploy_async(self, note: str):
        self.status.setText(f'Deploying... ({note})')
        self.worker = DeployWorker(self.launcher)
        self.worker.done.connect(self._deploy_done)
        self.worker.start()

    def _deploy_done(self, results: list):
        errs = [r for r in results if str(r[1]).startswith('failed')]
        self.status.setText('Deploy OK.' if not errs else f'Deploy finished with {len(errs)} error(s).')
        self.reload()

    def _backup_list(self):
        p = self._selected()
        if p:
            QMessageBox.information(self, 'Backup', 'Originals are backed up automatically\n'
                                    'as <file>.original.bak on first overwrite.')

    def _restore_originals(self):
        p = self._selected()
        if not p:
            return
        self.launcher.db_manager.set_dlc_enabled(p['id'], False)
        self._deploy_async(f"{p['id']} restored")

    # -- BACKUPS drawer (location + originals + uninstalled restore) ---------
    def _toggle_backups_slide(self):
        show = self.backups_slide.maximumHeight() == 0
        if show:
            self._fill_uninstalled()
        self.backups_slide.setVisible(True)
        self.backups_anim.stop()
        self.backups_anim.setStartValue(self.backups_slide.maximumHeight())
        self.backups_anim.setEndValue(190 if show else 0)
        try:
            self.backups_anim.finished.disconnect()
        except Exception:
            pass
        if not show:
            self.backups_anim.finished.connect(
                lambda: self.backups_slide.setVisible(False))
        self.backups_anim.start()

    def _open_backup_folder(self):
        target = _data_dir() / 'backups'
        try:
            target.mkdir(parents=True, exist_ok=True)
            os.startfile(str(target))
        except Exception as e:
            self.status.setText(f'backup folder failed: {e}')

    def _fill_uninstalled(self):
        import json
        self.uninst_listw.clear()
        vault = _data_dir() / 'uninstalled'
        if not vault.exists():
            return
        for p in sorted(vault.iterdir()):
            if not p.is_dir():
                continue
            meta = {}
            try:
                with open(p / 'origin.json', encoding='utf-8') as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                pass
            label = f"{meta.get('name', p.name)}  (from {meta.get('from', '?')}, {meta.get('ts', '?')})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, str(p))
            self.uninst_listw.addItem(item)

    def _restore_uninstalled(self):
        import shutil
        from managers import install_tracker as it
        items = self.uninst_listw.selectedItems()
        if not items:
            self.status.setText('BACKUPS: select an uninstalled mod first')
            return
        _on, off_dir = self._ml_dirs()
        done, skipped = [], []
        for item in items:
            src = Path(item.data(Qt.UserRole))
            name = src.name.split('_20')[0]
            dst = off_dir / name
            if not src.exists():
                skipped.append(src.name)
                continue
            if dst.exists():
                skipped.append(f'{name} (already present)')
                continue
            try:
                (src / 'origin.json').unlink(missing_ok=True)
                shutil.move(str(src), str(dst))
                it.record(name, 'restored', it.scan_tree(dst))
                done.append(name)
            except OSError:
                skipped.append(name)
        msg = f'RESTORED {len(done)} -> modloader_back (disabled)'
        if skipped:
            msg += f' (skipped: {", ".join(skipped)})'
        self.status.setText(msg)
        self._fill_uninstalled()
        self._fill_modloader()

    def _open_ariane(self):
        import subprocess
        ariane = Path(self.launcher.game_path) / 'ariane.exe'
        if ariane.exists():
            subprocess.Popen([str(ariane)], cwd=str(ariane.parent))
        else:
            QMessageBox.warning(self, 'ariane.exe missing',
                                f'Not found: {ariane}')

    def _edit_txd(self):
        game = getattr(self.launcher, 'game_path', None) or getattr(self.launcher, 'game_dir', None) or os.environ.get('GTA_PATH') or str(HERE)
        start = str(Path(game) / 'models')
        path, _ = QFileDialog.getOpenFileName(self, 'Open TXD', start, 'TXD (*.txd)')
        if not path:
            return
        try:
            dlg = TxdEditorDialog(path, self)
            dlg.exec_()
        except Exception as e:
            QMessageBox.warning(self, 'TXD open failed', str(e))

    # -- packs: ordered mod bundles applied to modloader ----------------------
    def _load_presets(self) -> list[dict]:
        f = _data_dir() / 'packs' / 'presets.json'
        if not f.exists():
            return []
        try:
            return json.loads(f.read_text(encoding='utf-8')).get('packs', [])
        except (OSError, ValueError):
            return []

    def _apply_pack(self, pack: dict):
        """Enable pack mods in modloader/ (NO renaming — folder names and any
        manual ordering the user made stay untouched). Mods not in the pack
        move to modloader_back/. 'order' is documentation only."""
        import shutil
        on_dir, off_dir = self._ml_dirs()
        on_dir.mkdir(parents=True, exist_ok=True)
        off_dir.mkdir(parents=True, exist_ok=True)
        wanted = list(pack.get('order', []))
        disabled = set(pack.get('disabled', []))
        moved_in = moved_out = 0
        for name in wanted:
            src = on_dir / name
            if not src.exists():
                src = off_dir / name
            if not src.exists():
                self.status.setText(f'pack: missing mod folder "{name}" — skipped')
                continue
            dst = on_dir / name
            if src != dst:
                shutil.move(str(src), str(dst))
                moved_in += 1
        for d in list(on_dir.iterdir()):
            if d.is_dir() and (d.name not in wanted or d.name in disabled):
                shutil.move(str(d), str(off_dir / d.name))
                moved_out += 1
        self._fill_modloader()
        self.status.setText(f"pack '{pack.get('name', pack.get('id'))}' applied — "
                            f"{len(wanted)} enabled, {moved_out} moved out")

    def _on_pack_selected(self, text: str):
        if text == self._PACK_NONE:
            return
        for p in self._load_presets():
            if p.get('name') == text or p.get('id') == text:
                if QMessageBox.question(
                        self, 'Apply pack',
                        f"Apply '{p.get('name')}'?\n\nThis re-orders modloader "
                        f"folders and disables mods not in the pack.") == QMessageBox.Yes:
                    self._apply_pack(p)
                break

    _PACK_NONE = '(choose pack…)'

    # -- Mod Loader folder view (Skyrim-style quick toggles) ------------------
    def _ml_dirs(self):
        root = self._game_root()
        return root / 'modloader', root / 'modloader_back'

    def _fill_modloader(self):
        self.ml_listw.clear()
        on_dir, off_dir = self._ml_dirs()
        for d, mark in ((on_dir, '[ON] '), (off_dir, '[OFF] ')):
            if not d.exists():
                continue
            for p in sorted(d.iterdir()):
                if p.is_dir() and not p.name.startswith('.'):
                    item = QListWidgetItem(f'{mark}{p.name}')
                    item.setData(Qt.UserRole, (str(p), mark == '[ON] '))
                    self.ml_listw.addItem(item)

    def _toggle_modloader(self, item):
        path, enabled = item.data(Qt.UserRole)
        src, dst_on = Path(path), None
        on_dir, off_dir = self._ml_dirs()
        dst = off_dir if enabled else on_dir
        try:
            dst.mkdir(parents=True, exist_ok=True)
            target = dst / src.name
            if target.exists():
                QMessageBox.warning(self, 'Mod Loader',
                                    f'{target.name} already exists in {dst.name}')
                return
            src.rename(target)
            self.status.setText(f"{'disabled' if enabled else 'enabled'} {src.name}")
        except OSError as e:
            QMessageBox.warning(self, 'Mod Loader', f'move failed: {e}')
        self._fill_modloader()

    # -- INSTALL slide-out (zip/folder -> readme-named -> modloader_back) ----
    def _toggle_install_slide(self):
        show = self.install_slide.maximumHeight() == 0
        self.install_slide.setVisible(True)
        self.install_anim.stop()
        self.install_anim.setStartValue(self.install_slide.maximumHeight())
        self.install_anim.setEndValue(46 if show else 0)
        try:
            self.install_anim.finished.disconnect()
        except Exception:
            pass
        if not show:
            self.install_anim.finished.connect(
                lambda: self.install_slide.setVisible(False))
        self.install_anim.start()

    def _install_from_zip(self):
        import zipfile
        from managers import archive_probe as ap, install_tracker as it
        fn, _ = QFileDialog.getOpenFileName(
            self, 'Select mod archive', '', 'Archives (*.zip)')
        if not fn:
            return
        try:
            names = ap.list_archive(fn)
        except Exception as e:
            self.status.setText(f'install failed: {e}')
            return
        readme_text = ''
        readme_rel = ap.find_readme(names)
        if readme_rel:
            try:
                with zipfile.ZipFile(fn) as zf:
                    readme_text = zf.read(readme_rel).decode(
                        'utf-8', errors='replace')
            except Exception:
                pass
        name, ok = QInputDialog.getText(
            self, 'Install mod', 'Folder name:',
            text=ap.suggest_pack_name(fn, names, readme_text))
        if not ok or not name.strip():
            return
        name = name.strip()
        _on, off_dir = self._ml_dirs()
        dst = off_dir / name
        if dst.exists():
            self.status.setText(f'{name} already installed')
            return
        try:
            dst.mkdir(parents=True)
            with zipfile.ZipFile(fn) as zf:
                zf.extractall(dst)
            files = it.scan_tree(dst)
            it.record(name, 'zip:' + Path(fn).name, files)
            self.status.setText(
                f'INSTALLED (disabled): {name} ({len(files)} files tracked)')
        except OSError as e:
            self.status.setText(f'install failed: {e}')
        self._fill_modloader()

    def _install_from_folder(self):
        import shutil
        from managers import install_tracker as it
        src = QFileDialog.getExistingDirectory(self, 'Select mod folder')
        if not src:
            return
        name, ok = QInputDialog.getText(
            self, 'Install mod', 'Folder name:', text=Path(src).name)
        if not ok or not name.strip():
            return
        name = name.strip()
        _on, off_dir = self._ml_dirs()
        dst = off_dir / name
        if dst.exists():
            self.status.setText(f'{name} already installed')
            return
        try:
            shutil.copytree(src, dst)
            files = it.scan_tree(dst)
            it.record(name, 'folder:' + Path(src).name, files)
            self.status.setText(
                f'INSTALLED (disabled): {name} ({len(files)} files tracked)')
        except OSError as e:
            self.status.setText(f'install failed: {e}')
        self._fill_modloader()

    def _toggle_filter_slide(self):
        show = self.filter_slide.maximumHeight() == 0
        self.filter_slide.setVisible(True)
        self.filter_anim.stop()
        self.filter_anim.setStartValue(self.filter_slide.maximumHeight())
        self.filter_anim.setEndValue(40 if show else 0)
        try:
            self.filter_anim.finished.disconnect()
        except Exception:
            pass
        if not show:
            self.filter_anim.finished.connect(
                lambda: self.filter_slide.setVisible(False))
        self.filter_anim.start()

    def _issue_filters(self):
        on = set()
        if self.ck_txd.isChecked():
            on.add('txd')
        if self.ck_mip.isChecked():
            on.add('mipmap')
        if self.ck_orph.isChecked():
            on.add('orphan')
        if self.ck_raw.isChecked():
            on.add('rawcfg')
        return on or {'txd', 'mipmap', 'orphan', 'rawcfg'}

    # -- UNINSTALL (multi-select -> uninstalled vault, restorable) ------------
    def _uninstall_selected(self):
        import json
        import shutil
        from datetime import datetime
        from managers import install_tracker as it
        items = self.ml_listw.selectedItems()
        if not items:
            self.status.setText('UNINSTALL: select mod folders first (multi-select OK)')
            return
        vault = _data_dir() / 'uninstalled'
        try:
            vault.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.status.setText(f'UNINSTALL failed (vault): {e}')
            return
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        moved, skipped = [], []
        for item in items:
            path, _enabled = item.data(Qt.UserRole)
            src = Path(path)
            if not src.exists() or not src.is_dir():
                skipped.append(src.name)
                continue
            dest = vault / f'{src.name}_{stamp}'
            try:
                shutil.move(str(src), str(dest))
                with open(dest / 'origin.json', 'w', encoding='utf-8') as f:
                    json.dump({'name': src.name,
                               'from': 'modloader_back' if 'modloader_back' in str(src) else 'modloader',
                               'ts': stamp}, f)
                it.unregister(src.name)
                moved.append(src.name)
            except OSError:
                skipped.append(src.name)
        msg = f'UNINSTALLED {len(moved)} -> vault'
        if skipped:
            msg += f' (skipped: {", ".join(skipped)})'
        self.status.setText(msg)
        self._fill_modloader()

    # -- modloader context menu (Wrye Bash parity actions) --------------------
    def _show_text_dialog(self, title, text):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(560, 420)
        lay = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(text)
        te.setStyleSheet(
            f"QTextEdit {{ background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BODY};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; font-family:Consolas; font-size:11px; }}")
        lay.addWidget(te)
        cb = ActionButton('CLOSE')
        cb.clicked.connect(dlg.accept)
        lay.addWidget(cb)
        dlg.exec_()

    def _ml_context_menu(self, pos):
        menu = QMenu(self)
        item = self.ml_listw.itemAt(pos)
        if item:
            path, enabled = item.data(Qt.UserRole)
            name = Path(path).name
            menu.addAction('Enable' if not enabled else 'Disable',
                           lambda: self._toggle_modloader(item))
            menu.addSeparator()
            menu.addAction('Show conflicts',
                           lambda: self._ml_show_conflicts(name))
            menu.addAction('Anneal / verify files',
                           lambda: self._ml_anneal(name, path))
            menu.addSeparator()
            menu.addAction('Priority +10',
                           lambda: self._ml_priority(name, +10))
            menu.addAction('Priority -10',
                           lambda: self._ml_priority(name, -10))
            menu.addSeparator()
            menu.addAction('Uninstall to vault', self._uninstall_selected)
        else:
            menu.addAction('Rescan folders', self._fill_modloader)
        menu.exec_(self.ml_listw.mapToGlobal(pos))

    def _ml_show_conflicts(self, name):
        from managers import conflict_detector as cd
        rep = cd.detect_conflicts(focus=name)
        lines = []
        for c in rep['conflicts']:
            others = [p['name'] for p in c['packs'] if p['name'] != name]
            if others:
                lines.append(f"{c['rel']}  <->  {', '.join(others)}")
        self._show_text_dialog(
            f'Conflicts — {name}',
            '\n'.join(lines) if lines else
            'No file conflicts with other tracked packs.\n'
            '(Only tracked installs are compared — install via INSTALL to track.)')

    def _ml_anneal(self, name, path):
        from managers import install_tracker as it
        rep = it.anneal(name, path)
        total = sum(len(v) for v in rep.values())
        if total == 0 and not it.installed_files(name):
            self.status.setText(f'{name}: not tracked — reinstall via INSTALL to track')
            return
        lines = [f"ok: {len(rep['ok'])}, missing: {len(rep['missing'])}, "
                 f"modified-outside-launcher: {len(rep['mismatched'])}"]
        for rel in rep['missing'][:50]:
            lines.append(f'  MISSING: {rel}')
        for rel in rep['mismatched'][:50]:
            lines.append(f'  MODIFIED: {rel} (kept, never auto-overwritten)')
        self._show_text_dialog(f'Anneal — {name}', '\n'.join(lines))

    def _ml_priority(self, name, delta):
        import re
        ini = self._game_root() / 'modloader' / 'modloader.ini'
        try:
            text = ini.read_text(encoding='utf-8', errors='replace')
        except OSError as e:
            self.status.setText(f'priority failed: {e}')
            return
        key, sec, cur = name.lower(), '[Profiles.Default.Priority]', 50
        if sec not in text:
            text = text.rstrip('\n') + f'\n\n{sec}\n'
        pat = re.compile(r'(?m)^' + re.escape(key) + r'\s*=\s*\d+')
        mm = pat.search(text)
        if mm:
            cur = int(re.search(r'\d+', mm.group(0)).group(0))
        new = max(0, min(100, cur + delta))
        text = (pat.sub(f'{key} = {new}', text, count=1) if mm
                else text.replace(sec, sec + f'\n{key} = {new}', 1))
        try:
            ini.write_text(text, encoding='utf-8')
            self.status.setText(f'priority: {name} {cur} -> {new} (ML reads on next boot)')
        except OSError as e:
            self.status.setText(f'priority failed: {e}')

    # -- drag-drop mod install (zip/folder -> modloader/) ---------------------
    def _ml_drag_enter(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def _ml_drop(self, ev):
        import shutil
        import zipfile
        on_dir, _ = self._ml_dirs()
        on_dir.mkdir(parents=True, exist_ok=True)
        installed = []
        for url in ev.mimeData().urls():
            src = Path(url.toLocalFile())
            if not src.exists():
                continue
            try:
                if src.is_file() and src.suffix.lower() == '.zip':
                    name = src.stem
                    dst = on_dir / name
                    if dst.exists():
                        QMessageBox.warning(self, 'Install', f'{name} already installed')
                        continue
                    dst.mkdir(parents=True)
                    with zipfile.ZipFile(src) as zf:
                        zf.extractall(dst)
                    installed.append(name)
                elif src.is_dir():
                    dst = on_dir / src.name
                    if dst.exists():
                        QMessageBox.warning(self, 'Install', f'{src.name} already installed')
                        continue
                    shutil.copytree(src, dst)
                    installed.append(src.name)
            except Exception as e:
                QMessageBox.warning(self, 'Install failed', f'{src.name}: {e}')
        self._fill_modloader()
        if installed:
            self.status.setText(f"installed: {', '.join(installed)} — double-click to toggle")

    # -- TXD health scanner ---------------------------------------------------
    def _game_root(self) -> Path:
        game = getattr(self.launcher, 'game_path', None) or getattr(self.launcher, 'game_dir', None) or os.environ.get('GTA_PATH')
        return Path(game or HERE)

    def _scan_txds(self):
        """Category-dispatched issue scan (FILTERS row selects categories)."""
        from managers import mapdata
        cats = self._issue_filters()
        roots = [self._game_root() / 'modloader', self._game_root() / 'modloader_back']
        self.listw.clear()
        self._scan_results = []
        counts = {'txd': 0, 'mipmap': 0, 'orphan': 0, 'rawcfg': 0}
        total = 0
        dff_refs: set = set()
        dff_packs: set = set()
        if 'orphan' in cats:
            for root in roots:
                if not root.exists():
                    continue
                for p in sorted(root.rglob('*.dff')):
                    try:
                        dff_refs |= mapdata.dff_texture_refs(p.read_bytes())
                        dff_packs.add(str(p.relative_to(root)).split('/')[0])
                    except Exception:
                        pass
                for img in sorted(root.rglob('*.img')):
                    try:
                        for name, off, size in mapdata.read_img_entries(str(img)):
                            if not name.endswith('.dff'):
                                continue
                            with open(str(img), 'rb') as fh:
                                fh.seek(off)
                                dff_refs |= mapdata.dff_texture_refs(fh.read(size))
                            dff_packs.add(str(img.relative_to(root)).split('/')[0])
                    except Exception:
                        pass
        for root in roots:
            if not root.exists():
                continue
            for p in sorted(root.rglob('*.txd')):
                total += 1
                try:
                    txd = txdlite.TxdFile.load(str(p))
                except Exception as e:
                    if 'txd' in cats:
                        item = QListWidgetItem(f'[CORRUPT] {p.relative_to(root.parent)}  ({e})')
                        item.setForeground(QColor(T.COLOR_YELLOW))
                        self.listw.addItem(item)
                        self._scan_results.append((p, None))
                        counts['txd'] += 1
                    continue
                strict = [i for t in txd.textures for i in txdlite.mip_issues(t, strict=True)]
                loose = [i for t in txd.textures for i in txdlite.mip_issues(t, strict=False)]
                rel = p.relative_to(root.parent)
                if strict and 'txd' in cats:
                    counts['txd'] += 1
                    item = QListWidgetItem(f'[BROKEN] {rel}  — {len(strict)} issue(s)')
                    item.setForeground(QColor(T.COLOR_YELLOW))
                    self.listw.addItem(item)
                    self._scan_results.append((p, strict))
                elif loose and 'mipmap' in cats:
                    counts['mipmap'] += 1
                    item = QListWidgetItem(f'[MIPMAP] {rel}  — could add mips ({len(loose)})')
                    item.setForeground(QColor(T.COLOR_TEXT_DIM))
                    self.listw.addItem(item)
                elif not strict and not loose and 'txd' in cats:
                    item = QListWidgetItem(f'[OK] {rel}')
                    item.setForeground(QColor(T.COLOR_TEXT_DIM))
                    self.listw.addItem(item)
                if 'orphan' in cats and dff_refs:
                    try:
                        names = {str(getattr(t, 'name', '')).lower() for t in txd.textures}
                    except Exception:
                        names = set()
                    names.discard('')
                    pack = str(rel).replace('\\', '/').split('/')
                    pack = pack[1] if len(pack) > 1 else ''
                    if names and pack in dff_packs and not (names & dff_refs):
                        counts['orphan'] += 1
                        if counts['orphan'] <= 200:
                            item = QListWidgetItem(f'[ORPHAN TXD] {rel}  — no DFF references it')
                            item.setForeground(QColor(T.COLOR_TEXT_DIM))
                            self.listw.addItem(item)
                if counts['orphan'] == 201:
                    item = QListWidgetItem('[ORPHAN TXD] … capped at 200 rows, see AUDIT tab for full list')
                    item.setForeground(QColor(T.COLOR_TEXT_DIM))
                    self.listw.addItem(item)
        if 'orphan' in cats:
            try:
                rep = mapdata.audit_mod_textures(str(self._game_root()))
                for name in sorted(rep.get('unresolved', {}))[:40]:
                    counts['orphan'] += 1
                    item = QListWidgetItem(f'[ORPHAN REF] {name}')
                    item.setForeground(QColor(T.COLOR_YELLOW))
                    self.listw.addItem(item)
            except Exception as e:
                self.status.setText(f'orphan audit failed: {e}')
                return
        if 'rawcfg' in cats:
            counts['rawcfg'] = self._scan_rawcfg()
        self.status.setText(
            f'scanned {total} TXDs — BROKEN {counts["txd"]}, MIPMAP {counts["mipmap"]}, '
            f'ORPHAN {counts["orphan"]}, RAWCFG {counts["rawcfg"]}')

    def _scan_rawcfg(self):
        """Raw data-file sanity: IDE duplicate model IDs, txdp syntax, gta.dat."""
        import re
        roots = [self._game_root() / 'modloader', self._game_root() / 'modloader_back']
        found = 0
        idmap = {}
        for root in roots:
            if not root.exists():
                continue
            for p in sorted(root.rglob('*.ide')):
                try:
                    text = p.read_text(encoding='utf-8', errors='replace')
                except OSError:
                    continue
                section = None
                for ln in text.splitlines():
                    s = ln.strip().lower()
                    if not s or s.startswith(('#', '//', ';')):
                        continue
                    if s in ('objs', 'tobj', 'hier', 'txdp', 'anim', 'cars', 'peds',
                             'weap', '2dfx', 'end'):
                        section = None if s == 'end' else s
                        continue
                    if section in ('objs', 'tobj'):
                        parts = [x.strip() for x in ln.split(',')]
                        if len(parts) >= 2 and parts[0].isdigit():
                            rel = str(p.relative_to(root.parent)).replace('\\', '/')
                            segs = rel.split('/')
                            pack = segs[1] if len(segs) > 1 else segs[0]
                            idmap.setdefault(parts[0], []).append((pack, parts[1].lower()))
                    elif section == 'txdp':
                        if not re.match(r'^\s*[\w\-\.]+\s*,\s*[\w\-\.]+\s*$', ln):
                            found += 1
                            item = QListWidgetItem(f'[RAWCFG] {p.relative_to(root.parent)} — bad txdp line: {ln.strip()[:60]}')
                            item.setForeground(QColor(T.COLOR_YELLOW))
                            self.listw.addItem(item)
        for _id, where in sorted(idmap.items(), key=lambda kv: int(kv[0])):
            packs = {p for p, _m in where}
            models = {m for _p, m in where}
            if len(packs) > 1 and len(models) > 1:
                found += 1
                if found <= 200:
                    item = QListWidgetItem(
                        f'[RAWCFG] model id {_id} redefined: ' +
                        ', '.join(f'{m} ({p})' for p, m in sorted(set(where))[:4]))
                    item.setForeground(QColor(T.COLOR_YELLOW))
                    self.listw.addItem(item)
        if found > 200:
            item = QListWidgetItem(f'[RAWCFG] … {found - 200} more redefined ids (see AUDIT tab)')
            item.setForeground(QColor(T.COLOR_TEXT_DIM))
            self.listw.addItem(item)
        if not (self._game_root() / 'data' / 'gta.dat').exists():
            found += 1
            item = QListWidgetItem('[RAWCFG] game data/gta.dat missing!')
            item.setForeground(QColor(T.COLOR_YELLOW))
            self.listw.addItem(item)
        return found

    def _fix_all_txds(self):
        if not getattr(self, '_scan_results', None):
            self.status.setText('run SCAN FOR ISSUES first (TXDs category on)')
            return
        targets = [(p, iss) for p, iss in self._scan_results if iss]
        if not targets:
            self.status.setText('nothing to fix — all scanned TXDs are healthy')
            return
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        bdir = HERE / 'launcher_data' / 'backups' / f'txd_mipfix_{stamp}'

        dlg = QProgressDialog(
            f'Fixing mipmaps in {len(targets)} TXDs…', 'CANCEL', 0, len(targets), self)
        dlg.setWindowTitle('TXD Mipmap Fix')
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setStyleSheet(
            f"QProgressDialog {{ background:{T.COLOR_PANEL_BG}; color:{T.COLOR_TEXT_BODY}; }}"
            f"QProgressBar {{ background:{T.COLOR_PANEL_BG_LIGHT};"
            f" border:1px solid {T.COLOR_DARK_GREEN}; color:{T.COLOR_TEXT_BODY};"
            f" text-align:center; }}"
            f"QProgressBar::chunk {{ background:{T.COLOR_GROVE_GREEN}; }}")
        fixed = failed = 0
        for i, (p, _issues) in enumerate(targets):
            dlg.setLabelText(f'[{i + 1}/{len(targets)}] {p.name}')
            dlg.setValue(i)
            if dlg.wasCanceled():
                break
            # per-file backup FIRST, then fix, then save immediately —
            # a crash mid-batch loses nothing; every completed file persists
            try:
                bdir.mkdir(parents=True, exist_ok=True)
                (bdir / p.name).write_bytes(p.read_bytes())   # backup original
            except Exception as e:
                failed += 1
                self.status.setText(f'backup failed {p.name}: {e}')
                continue
            try:
                txd = txdlite.TxdFile.load(str(p))
            except Exception:
                failed += 1
                continue
            changed = False
            for t in txd.textures:
                if txdlite.mip_issues(t):
                    try:
                        txdlite.fix_texture_mips(t)
                        changed = True
                    except Exception:
                        pass
            if not changed:
                (bdir / p.name).unlink(missing_ok=True)  # healthy: drop backup
                continue
            try:
                txd.save(str(p))                          # write fixed immediately
                fixed += 1
            except Exception as e:
                failed += 1
                self.status.setText(f'fix failed {p.name}: {e}')
        dlg.setValue(len(targets))
        cancelled = dlg.wasCanceled()
        dlg.close()
        verb = 'stopped after' if cancelled else 'fixed'
        self.status.setText(
            f'{verb} {fixed} TXDs ({failed} failed) — originals in {bdir}')
        QMessageBox.information(
            self, 'TXD Mipmap Fix',
            f'{fixed} TXD file(s) fixed, {failed} failed.\n'
            f'Originals backed up to:\n{bdir}\n\n'
            f'Re-scanning to confirm warnings are cleared…')
        self._scan_txds()
        left = sum(1 for _p, iss in getattr(self, '_scan_results', []) if iss)
        QMessageBox.information(
            self, 'TXD Mipmap Fix',
            f'Done. {fixed} fixed, {failed} failed, {left} warning(s) remaining.'
            if left else
            f'All clear — every scanned TXD is healthy now. '
            f'({fixed} fixed, {failed} failed)')

    def _filter(self, cats):
        self.filter = cats
        self._fill_list()

    def _show_details(self, _row: int):
        p = self._selected()
        if not p:
            return
        lines = [f"name:     {p.get('name')}",
                 f"id:       {p['id']}",
                 f"category: {p.get('category')}",
                 f"layer:    {p.get('layer', '-')}   order: {p.get('order', '-')}",
                 f"mode:     {p.get('deploy_mode', 'modloader')}",
                 f"files:    {p.get('file_count', '?')}   bytes: {p.get('bytes', 0):,}",
                 f"enabled:  {p['_enabled']}"]
        st = p.get('stats') or {}
        if st:
            lines.append('content:')
            lines.append(json.dumps(st, indent=2)[:1200])
        files = p.get('files') or []
        if files:
            lines.append('files (first 25):')
            for f in files[:25]:
                lines.append(f"  {f.get('path', f)}")
        self.details.setPlainText('\n'.join(lines))


# =============================================================================
# INSTALLER screen
# =============================================================================

FILTER_MODES = [('NONE', 0), ('NEAREST', 1), ('LINEAR', 2), ('MIPNEAREST', 3),
                ('MIPLINEAR', 4), ('LINEARMIPNEAREST', 5), ('LINEARMIPLINEAR', 6)]
ADDR_MODES = [('WRAP', 0), ('MIRROR', 1), ('CLAMP', 2), ('BORDER', 3)]
TXD_FORMATS = ['auto', '8888', 'DXT1', 'DXT3', 'DXT5']


class TxdViewport(QWidget):
    """Zoomable/pannable texture viewport with checkerboard background."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix: QPixmap | None = None
        self._zoom = 1.0
        self._off = [0, 0]
        self._drag = None
        self.setMinimumSize(300, 300)
        self.setStyleSheet(f"background:{T.COLOR_PANEL_BG};")

    def set_image(self, img=None):
        if img is None:
            self._pix = None
        else:
            self._buf = img.tobytes('raw', 'RGBA')
            self._pix = QPixmap.fromImage(
                QImage(self._buf,
                       img.width, img.height, QImage.Format_RGBA8888))
            self._zoom = 1.0
            self._off = [0, 0]
        self.update()

    def wheelEvent(self, ev):  # noqa: N802
        if not self._pix:
            return
        factor = 1.25 if ev.angleDelta().y() > 0 else 0.8
        self._zoom = max(0.05, min(32.0, self._zoom * factor))
        self.update()

    def mousePressEvent(self, ev):  # noqa: N802
        if ev.button() == Qt.LeftButton:
            self._drag = (ev.pos().x() - self._off[0], ev.pos().y() - self._off[1])

    def mouseMoveEvent(self, ev):  # noqa: N802
        if self._drag:
            self._off = [ev.pos().x() - self._drag[0], ev.pos().y() - self._drag[1]]
            self.update()

    def mouseReleaseEvent(self, ev):  # noqa: N802
        self._drag = None

    def paintEvent(self, ev):  # noqa: N802
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(T.COLOR_PANEL_BG))
        # checkerboard
        cs = 16
        for y in range(0, h, cs):
            for x in range(0, w, cs):
                if (x // cs + y // cs) % 2 == 0:
                    p.fillRect(x, y, cs, cs, QColor(T.COLOR_CHECKER))
        if not self._pix:
            p.setPen(QColor(T.COLOR_TEXT_DIM))
            p.drawText(self.rect(), Qt.AlignCenter, 'no texture')
            return
        t = self._transform()
        p.setRenderHint(QPainter.SmoothPixmapTransform, self._zoom < 4.0)
        p.drawPixmap(t[0], t[1], t[2], t[3], self._pix)

    def _transform(self):
        pw, ph = self._pix.width() * self._zoom, self._pix.height() * self._zoom
        return (int((self.width() - pw) / 2 + self._off[0]),
                int((self.height() - ph) / 2 + self._off[1]),
                int(pw), int(ph))


class PixelEditDialog(QDialog):
    """Floating quick pixel editor — Pinta tool port (pencil/brush/eraser/
    bucket/picker/zoom, undo/redo) for dirty texture edits."""

    TOOLS = ('pencil', 'brush', 'eraser', 'bucket', 'picker', 'pan')

    def __init__(self, pil_image, title='Quick Edit', parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Window)  # movable, own taskbar entry
        self.resize(900, 640)
        self.image = pil_image.convert('RGBA')
        self._undo: list = []
        self._redo: list = []
        self._tool = 'pencil'
        self._color = (255, 255, 0, 255)
        self._size = 2
        self._zoom = max(1, min(8, 512 // max(self.image.width, 1)))
        self._pan = [0, 0]
        self._drawing = False
        self._last = None
        self._pan_from = None

        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        for name in self.TOOLS:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setChecked(name == self._tool)
            b.clicked.connect(lambda _, n=name: self._pick_tool(n))
            b.setStyleSheet(
                f"QPushButton {{ background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BODY};"
                f"border:1px solid {T.COLOR_DARK_GREEN}; padding:4px 10px; }}"
                f"QPushButton:checked {{ background:{T.COLOR_GROVE_GREEN}; color:#04140a; }}")
            self._tool_btns = getattr(self, '_tool_btns', {})
            self._tool_btns[name] = b
            bar.addWidget(b)
        bar.addStretch(1)
        undo_b = QPushButton('undo')
        undo_b.clicked.connect(self._undo_fn)
        redo_b = QPushButton('redo')
        redo_b.clicked.connect(self._redo_fn)
        for b in (undo_b, redo_b):
            b.setStyleSheet(f"QPushButton {{ background:{T.COLOR_PANEL_BG_LIGHT};"
                            f"color:{T.COLOR_TEXT_BODY}; border:1px solid {T.COLOR_DARK_GREEN};"
                            f"padding:4px 10px; }}")
            bar.addWidget(b)
        lay.addLayout(bar)

        bar2 = QHBoxLayout()
        bar2.addWidget(body('color'))
        self._color_swatch = QLabel()
        self._color_swatch.setFixedSize(28, 20)
        self._update_swatch()
        self._color_swatch.mousePressEvent = lambda ev: self._pick_color()
        bar2.addWidget(self._color_swatch)
        bar2.addWidget(body('size'))
        self._size_spin = QSpinBox()
        self._size_spin.setRange(1, 64)
        self._size_spin.setValue(self._size)
        self._size_spin.valueChanged.connect(lambda v: setattr(self, '_size', v))
        bar2.addWidget(self._size_spin)
        bar2.addWidget(body('zoom'))
        self._zoom_spin = QSpinBox()
        self._zoom_spin.setRange(1, 32)
        self._zoom_spin.setValue(self._zoom)
        self._zoom_spin.valueChanged.connect(self._set_zoom)
        bar2.addWidget(self._zoom_spin)
        bar2.addStretch(1)
        ok = ActionButton('APPLY TO TEXTURE')
        ok.clicked.connect(self.accept)
        cancel = ActionButton('CANCEL', danger=True)
        cancel.clicked.connect(self.reject)
        bar2.addWidget(ok)
        bar2.addWidget(cancel)
        lay.addLayout(bar2)

        self.canvas = PixelCanvas(self)
        lay.addWidget(self.canvas, 1)
        self.status = body(f'{self.image.width}x{self.image.height}')
        lay.addWidget(self.status)

    # -- tool plumbing --------------------------------------------------------
    def _pick_tool(self, name):
        self._tool = name
        for n, b in self._tool_btns.items():
            b.setChecked(n == name)

    def _update_swatch(self):
        pm = QPixmap(28, 20)
        pm.fill(QColor(*self._color))
        self._color_swatch.setPixmap(pm)

    def _pick_color(self):
        from PyQt5.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(*self._color), self, 'Pick color')
        if c.isValid():
            self._color = (c.red(), c.green(), c.blue(), 255)
            self._update_swatch()

    def _set_zoom(self, z):
        self._zoom = z
        self.canvas.update()

    def _push_undo(self):
        self._undo.append(self.image.copy())
        if len(self._undo) > 40:
            self._undo.pop(0)
        self._redo.clear()

    def _undo_fn(self):
        if not self._undo:
            return
        self._redo.append(self.image.copy())
        self.image = self._undo.pop()
        self.canvas.update()

    def _redo_fn(self):
        if not self._redo:
            return
        self._undo.append(self.image.copy())
        self.image = self._redo.pop()
        self.canvas.update()

    def result_image(self):
        return self.image


class PixelCanvas(QWidget):
    """Shared-canvas widget for PixelEditDialog (Pinta canvas port)."""

    def __init__(self, dlg: PixelEditDialog):
        super().__init__(dlg)
        self.dlg = dlg
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self._flood_visited = None

    # coordinate mapping
    def _to_image(self, pos):
        d = self.dlg
        cw, ch = d.image.width * d._zoom, d.image.height * d._zoom
        ox = (self.width() - cw) // 2 + d._pan[0]
        oy = (self.height() - ch) // 2 + d._pan[1]
        return ((pos.x() - ox) // d._zoom, (pos.y() - oy) // d._zoom)

    # tools
    def _apply_line(self, x0, y0, x1, y1):
        d = self.dlg
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            self._apply_point(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def _apply_point(self, x, y):
        d = self.dlg
        w, h = d.image.width, d.image.height
        if not (0 <= x < w and 0 <= y < h):
            return
        if d._tool == 'pencil':
            d.image.putpixel((x, y), d._color)
        elif d._tool in ('brush', 'eraser'):
            r = max(0, d._size - 1)
            col = (0, 0, 0, 0) if d._tool == 'eraser' else d._color
            for yy in range(max(0, y - r), min(h, y + r + 1)):
                for xx in range(max(0, x - r), min(w, x + r + 1)):
                    if (xx - x) ** 2 + (yy - y) ** 2 <= r * r:
                        d.image.putpixel((xx, yy), col)
        elif d._tool == 'picker':
            d._color = d.image.getpixel((x, y))[:4]
            d._update_swatch()

    def _flood(self, x, y):
        d = self.dlg
        w, h = d.image.width, d.image.height
        if not (0 <= x < w and 0 <= y < h):
            return
        target = d.image.getpixel((x, y))
        if target == d._color:
            return
        from collections import deque
        q = deque([(x, y)])
        seen = {(x, y)}
        while q:
            cx, cy = q.popleft()
            d.image.putpixel((cx, cy), d._color)
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen \
                        and d.image.getpixel((nx, ny)) == target:
                    seen.add((nx, ny))
                    q.append((nx, ny))

    # events
    def mousePressEvent(self, ev):  # noqa: N802
        d = self.dlg
        x, y = self._to_image(ev.pos())
        if ev.button() == Qt.MiddleButton or d._tool == 'pan':
            self._pan_from = (ev.pos().x(), ev.pos().y())
            return
        d._push_undo()
        if d._tool == 'bucket':
            self._flood(x, y)
        elif d._tool == 'picker':
            self._apply_point(x, y)
        else:
            self._drawing = True
            self._last = (x, y)
            self._apply_point(x, y)
        self.update()

    def mouseMoveEvent(self, ev):  # noqa: N802
        d = self.dlg
        if self._pan_from:
            d._pan = [d._pan[0] + ev.pos().x() - self._pan_from[0],
                      d._pan[1] + ev.pos().y() - self._pan_from[1]]
            self._pan_from = (ev.pos().x(), ev.pos().y())
            self.update()
            return
        if not self._drawing:
            return
        x, y = self._to_image(ev.pos())
        self._apply_line(self._last[0], self._last[1], x, y)
        self._last = (x, y)
        self.update()

    def mouseReleaseEvent(self, ev):  # noqa: N802
        self._drawing = False
        self._pan_from = None

    def wheelEvent(self, ev):  # noqa: N802
        d = self.dlg
        z = max(1, min(32, d._zoom + (1 if ev.angleDelta().y() > 0 else -1)))
        d._zoom_spin.setValue(z)

    def paintEvent(self, ev):  # noqa: N802
        d = self.dlg
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.COLOR_RAISED))
        img = d.image
        cw, ch = img.width * d._zoom, img.height * d._zoom
        ox = (self.width() - cw) // 2 + d._pan[0]
        oy = (self.height() - ch) // 2 + d._pan[1]
        # checkerboard
        cs = max(4, d._zoom)
        for yy in range(0, img.height(), 1):
            for xx in range(0, img.width(), 1):
                if (xx + yy) % 2 == 0:
                    p.fillRect(ox + xx * d._zoom, oy + yy * d._zoom,
                               d._zoom, d._zoom, QColor(T.COLOR_CHECKER))
        self._buf = img.tobytes('raw', 'RGBA')
        qimg = QImage(self._buf, img.width, img.height,
                      QImage.Format_RGBA8888)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawImage(ox, oy, qimg, 0, 0, img.width, img.height)
        p.setPen(QColor(T.COLOR_DARK_GREEN))
        p.drawRect(ox - 1, oy - 1, cw + 1, ch + 1)


class TxdEditorScreen(ScreenBase):
    """Full TXD editor screen — GGMM workflow, Magic.TXD feature set."""

    def __init__(self, launcher=None, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        self.txd = None
        self.txd_path = None
        self.show_alpha = False
        self._thumb_q: list[int] = []

        root = self.root  # ScreenBase already installed the layout
        bar = QHBoxLayout()
        for label, slot in (('OPEN TXD', self._open), ('NEW TXD', self._new),
                            ('SAVE', self._save), ('SAVE AS', self._save_as),
                            ('EXPORT ALL', self._export_all)):
            b = ActionButton(label)
            b.clicked.connect(slot)
            bar.addWidget(b)
        self.alpha_cb = QCheckBox('alpha')
        self.alpha_cb.setStyleSheet(f"color:{T.COLOR_TEXT_BODY};")
        self.alpha_cb.toggled.connect(self._toggle_alpha)
        bar.addWidget(self.alpha_cb)
        credit = body('based on Magic.TXD by dk22pac', dim=True)
        bar.addWidget(credit)
        bar.addStretch(1)
        root.addLayout(bar)
        root.addWidget(self._build_menubar())

        mid = QHBoxLayout()
        self.listw = QListWidget()
        self.listw.setViewMode(QListWidget.IconMode)
        self.listw.setIconSize(QSize(64, 64))
        self.listw.setGridSize(QSize(96, 96))
        self.listw.setFixedWidth(220)
        self.listw.currentRowChanged.connect(self._on_select)
        mid.addWidget(self.listw)

        self.viewport = TxdViewport()
        mid.addWidget(self.viewport, 1)

        props = QVBoxLayout()
        props.addWidget(heading('PROPERTIES', 14, T.COLOR_WALKMAN_GREEN))
        self.p_name = QLineEdit()
        self.p_mask = QLineEdit()
        self.p_dims = body('-')
        self.p_fmt = body('-')
        self.p_mips = body('-')
        self.p_ver = body('-')
        for label, w in (('name', self.p_name), ('mask', self.p_mask)):
            row = QHBoxLayout()
            row.addWidget(body(label))
            row.addWidget(w)
            props.addLayout(row)
        for label, w in (('size', self.p_dims), ('format', self.p_fmt),
                         ('mips', self.p_mips),
                         ('rw ver', self.p_ver)):
            row = QHBoxLayout()
            row.addWidget(body(label))
            row.addWidget(w)
            props.addLayout(row)
        self.c_filter = QComboBox()
        self.c_addr_u = QComboBox()
        self.c_addr_v = QComboBox()
        for combo, modes in ((self.c_filter, FILTER_MODES), (self.c_addr_u, ADDR_MODES),
                             (self.c_addr_v, ADDR_MODES)):
            for txt, _v in modes:
                combo.addItem(txt)
        for label, combo in (('filter', self.c_filter), ('addr U', self.c_addr_u),
                             ('addr V', self.c_addr_v)):
            row = QHBoxLayout()
            row.addWidget(body(label))
            row.addWidget(combo)
            props.addLayout(row)
        self.c_filter.currentIndexChanged.connect(self._on_sampler)
        self.c_addr_u.currentIndexChanged.connect(self._on_sampler)
        self.c_addr_v.currentIndexChanged.connect(self._on_sampler)

        ops = QGridLayout()
        op_specs = [('REPLACE IMAGE', self._replace), ('ADD TEXTURE', self._add),
                    ('DELETE', self._delete), ('DUPLICATE', self._duplicate),
                    ('GEN MIPS', self._gen_mips), ('STRIP MIPS', self._strip_mips),
                    ('EXPORT PNG', self._export_one), ('EDIT', self._quick_edit)]
        for i, (label, slot) in enumerate(op_specs):
            b = ActionButton(label)
            b.clicked.connect(slot)
            ops.addWidget(b, i // 2, i % 2)
        props.addLayout(ops)
        props.addStretch(1)
        propsw = QWidget()
        propsw.setLayout(props)
        propsw.setFixedWidth(240)
        mid.addWidget(propsw)
        root.addLayout(mid, 1)

        self.status = body('Open a TXD to begin.')
        root.addWidget(self.status)

        self._thumb_timer = QTimer(self)
        self._thumb_timer.timeout.connect(self._pump_thumb)

    # -- Magic.TXD menu bar (translated from src/mainwindow.menu.cpp) ---------
    def _build_menubar(self) -> QMenuBar:
        mb = QMenuBar()
        mb.setStyleSheet(
            f"QMenuBar {{ background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BODY};"
            f"border-bottom:1px solid {T.COLOR_DARK_GREEN}; }}"
            f"QMenuBar::item:selected {{ background:{T.COLOR_DARK_GREEN}; }}"
            f"QMenu {{ background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BODY};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; }}"
            f"QMenu::item:selected {{ background:{T.COLOR_WALKMAN_ORANGE};"
            f" color:{T.COLOR_ON_ACCENT}; }}")

        m_file = mb.addMenu('File')
        for label, slot in (('New', self._new), ('Open…', self._open),
                            ('Save', self._save), ('Save As…', self._save_as),
                            ('Close', self._close_txd), ('Quit', self._quit)):
            a = m_file.addAction(label)
            a.triggered.connect(slot)

        m_edit = mb.addMenu('Edit')
        for label, slot in (('Add Texture…', self._add), ('Replace…', self._replace),
                            ('Remove', self._delete), ('Rename…', self._rename),
                            ('Resize…', self._resize),
                            ('Generate Mip Levels', self._gen_mips),
                            ('Clear Mip Levels', self._strip_mips),
                            ('Duplicate…', self._duplicate)):
            a = m_edit.addAction(label)
            a.triggered.connect(slot)

        m_tools = mb.addMenu('Tools')
        for label, slot in (('Mass Convert PNGs → TXD…', self._mass_convert),
                            ('Mass Export…', self._export_all)):
            a = m_tools.addAction(label)
            a.triggered.connect(slot)

        m_exp = mb.addMenu('Export')
        for ext in ('png', 'bmp', 'dds', 'tga'):
            a = m_exp.addAction(f'Current texture → {ext.upper()}…')
            a.triggered.connect(lambda _, e=ext: self._export_as(e))
        a = m_exp.addAction('Export All…')
        a.triggered.connect(self._export_all)

        m_view = mb.addMenu('View')
        a = m_view.addAction('Reset Zoom')
        a.triggered.connect(lambda: self.viewport.set_image(self._decoded(self._cur()))
                            if self._cur() else None)
        a = m_view.addAction('Show Alpha')
        a.setCheckable(True)
        a.setChecked(self.show_alpha)
        a.toggled.connect(self.alpha_cb.setChecked)

        m_info = mb.addMenu('Info')
        a = m_info.addAction('Open in Ariane (map editor)')
        a.triggered.connect(self._open_ariane)
        a = m_info.addAction('About')
        a.triggered.connect(self._about)
        return mb

    def _quit(self):
        self.window().close()

    def _close_txd(self):
        self.txd = None
        self.txd_path = None
        self._refresh_list()
        self.viewport.set_image(None)
        self.status.setText('closed.')

    def _rename(self):
        t = self._cur()
        if not t:
            return
        name, ok = QInputDialog.getText(self, 'Rename texture', 'new name:',
                                        text=t.name)
        if ok and name.strip():
            txdlite.texture_rename(t, name)
            self._refresh_list()
            self.status.setText(f'renamed to {t.name}')

    def _resize(self):
        t = self._cur()
        if not t:
            return
        w, ok = QInputDialog.getInt(self, 'Resize', 'width:', t.width, 1, 4096)
        if not ok:
            return
        h, ok = QInputDialog.getInt(self, 'Resize', 'height:', t.height, 1, 4096)
        if not ok:
            return
        try:
            txdlite.texture_resize(t, w, h)
            self._on_select(self.listw.currentRow())
            self.status.setText(f'resized {t.name} to {w}x{h}')
        except Exception as e:
            QMessageBox.warning(self, 'Resize failed', str(e))

    def _export_as(self, ext: str):
        t = self._cur()
        if not t:
            return
        out, _ = QFileDialog.getSaveFileName(self, 'Export texture', f'{t.name}.{ext}',
                                             f'{ext.upper()} (*.{ext})')
        if out:
            txdlite.decode_mip(t).save(out)
            self.status.setText(f'exported {t.name} → {out}')

    def _mass_convert(self):
        d = QFileDialog.getExistingDirectory(self, 'Folder of PNGs to pack into one TXD')
        if not d:
            return
        self._new()
        added = 0
        for p in sorted(Path(d).glob('*.png')):
            try:
                from PIL import Image
                self.txd.add_texture(Image.open(p), p.stem, 'auto')
                added += 1
            except Exception:
                pass
        self._refresh_list()
        self.status.setText(f'mass-converted {added} PNGs — SAVE AS to write TXD')

    def _open_ariane(self):
        import subprocess
        game = getattr(self.launcher, 'game_path', None) or os.environ.get('GTA_PATH')
        ariane = Path(game or HERE) / 'ariane.exe'
        if ariane.exists():
            subprocess.Popen([str(ariane)], cwd=str(ariane.parent))
            self.status.setText('launched ariane.exe')
        else:
            QMessageBox.warning(self, 'ariane.exe missing',
                                f'Not found: {ariane}\n\n'
                                'Copy ariane.exe next to gta_sa.exe to enable '
                                'map editing.')

    def _about(self):
        QMessageBox.about(
            self, 'TXD Editor',
            'GTA Bridge TXD Editor\npure-Python RenderWare engine (txdlite)\n\n'
            'Menu structure and feature set translated from Magic.TXD.\n'
            'Original tool and RW engine by dk22pac (with The_Hero / MIRATA).\n'
            'Spiritual successor to the GTA Garage Mod Manager (GGMM).\n\n'
            'https://github.com/dk22pac/Magic.TXD')

    # -- helpers --------------------------------------------------------------
    def _game_models(self) -> str:
        game = getattr(self.launcher, 'game_path', None) or getattr(self.launcher, 'game_dir', None) if self.launcher else None
        return str(Path(game or os.environ.get('GTA_PATH') or HERE) / 'models')

    def _cur(self):
        row = self.listw.currentRow()
        if self.txd and 0 <= row < len(self.txd.textures):
            return self.txd.textures[row]
        return None

    def _decoded(self, t):
        img = txdlite.decode_mip(t)
        if not self.show_alpha:
            solid = img.copy()
            solid.putalpha(255)
            return solid
        return img

    def _refresh_list(self):
        self.listw.clear()
        self._thumb_q = []
        if not self.txd:
            return
        for i, t in enumerate(self.txd.textures):
            it = QListWidgetItem(t.name)
            it.setData(Qt.UserRole, i)
            self.listw.addItem(it)
            self._thumb_q.append(i)
        self._thumb_timer.start(10)

    def _pump_thumb(self):
        if not self._thumb_q:
            self._thumb_timer.stop()
            return
        i = self._thumb_q.pop(0)
        t = self.txd.textures[i]
        try:
            img = txdlite.decode_mip(t)
            img.thumbnail((64, 64))
            buf = img.tobytes('raw', 'RGBA')
            self.listw.item(i).setIcon(
                QIcon(QPixmap.fromImage(QImage(buf, img.width, img.height,
                                               QImage.Format_RGBA8888))))
        except Exception:
            pass
        self.status.setText(f'loading previews… {len(self.txd.textures) - len(self._thumb_q)}'
                            f'/{len(self.txd.textures)}')

    def _on_select(self, row):
        t = self._cur()
        if not t:
            self.viewport.set_image(None)
            return
        try:
            self.viewport.set_image(self._decoded(t))
        except Exception as e:
            self.viewport.set_image(None)
            self.status.setText(f'decode failed: {e}')
            return
        self.p_name.setText(t.name)
        self.p_mask.setText(t.mask)
        self.p_dims.setText(f'{t.width} x {t.height}')
        self.p_fmt.setText(t.fmt_name())
        self.p_mips.setText(str(t.num_levels))
        if self.txd is not None:
            self.p_ver.setText(txdlite.version_friendly(self.txd.version))
        fa = t.filter_addressing
        self.c_filter.blockSignals(True)
        self.c_addr_u.blockSignals(True)
        self.c_addr_v.blockSignals(True)
        self.c_filter.setCurrentIndex(max(0, min(6, fa & 0xFF)))
        self.c_addr_u.setCurrentIndex((fa >> 8) & 0x3)
        self.c_addr_v.setCurrentIndex((fa >> 12) & 0x3)
        self.c_filter.blockSignals(False)
        self.c_addr_u.blockSignals(False)
        self.c_addr_v.blockSignals(False)

    def _on_sampler(self):
        t = self._cur()
        if not t:
            return
        fa = (self.c_filter.currentIndex()
              | (self.c_addr_u.currentIndex() << 8)
              | (self.c_addr_v.currentIndex() << 12))
        txdlite.texture_set_filter_addressing(t, fa)
        self.status.setText(f'filter/addressing updated for {t.name}')

    def _toggle_alpha(self, on):
        self.show_alpha = on
        t = self._cur()
        if t:
            self.viewport.set_image(self._decoded(t))

    # -- file ops -------------------------------------------------------------
    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open TXD', self._game_models(),
                                              'TXD (*.txd)')
        if not path:
            return
        try:
            self.txd = txdlite.TxdFile.load(path)
            self.txd_path = path
            self._refresh_list()
            self.status.setText(f'loaded {path} — {len(self.txd.textures)} textures')
        except Exception as e:
            QMessageBox.warning(self, 'Open failed', str(e))

    def _new(self):
        self.txd = txdlite.TxdFile.create()
        self.txd_path = None
        self._refresh_list()
        self.status.setText('new empty TXD — add textures, then SAVE AS')

    def _save(self):
        if not self.txd:
            return
        if not self.txd_path:
            return self._save_as()
        try:
            self.txd.save(self.txd_path)
            self.status.setText(f'saved {self.txd_path}')
        except Exception as e:
            QMessageBox.warning(self, 'Save failed', str(e))

    def _save_as(self):
        if not self.txd:
            return
        out, _ = QFileDialog.getSaveFileName(self, 'Save TXD',
                                             self.txd_path or self._game_models(),
                                             'TXD (*.txd)')
        if not out:
            return
        try:
            self.txd.save(out)
            self.txd_path = out
            self.status.setText(f'saved {out}')
        except Exception as e:
            QMessageBox.warning(self, 'Save failed', str(e))

    def _export_all(self):
        if not self.txd or not self.txd.textures:
            return
        d = QFileDialog.getExistingDirectory(self, 'Export all textures to')
        if not d:
            return
        ok = 0
        for t in self.txd.textures:
            try:
                txdlite.decode_mip(t).save(str(Path(d) / f'{t.name}.png'))
                ok += 1
            except Exception:
                pass
        self.status.setText(f'exported {ok}/{len(self.txd.textures)} PNGs to {d}')

    # -- texture ops ----------------------------------------------------------
    def _replace(self):
        t = self._cur()
        if not t:
            return
        src, _ = QFileDialog.getOpenFileName(self, 'Replace image', '',
                                             'Images (*.png *.jpg *.jpeg *.bmp)')
        if not src:
            return
        try:
            from PIL import Image
            self.txd.replace(t.name, Image.open(src))
            self._on_select(self.listw.currentRow())
            self.status.setText(f'replaced {t.name}')
        except Exception as e:
            QMessageBox.warning(self, 'Replace failed', str(e))

    def _add(self):
        if not self.txd:
            self._new()
        src, _ = QFileDialog.getOpenFileName(self, 'Add texture from image', '',
                                             'Images (*.png *.jpg *.jpeg *.bmp)')
        if not src:
            return
        name, ok = QInputDialog.getText(self, 'Texture name',
                                        Path(src).stem[:31])
        if not ok or not name.strip():
            return
        fmt, ok = QInputDialog.getItem(self, 'Format', 'encode as', TXD_FORMATS, 0, False)
        if not ok:
            return
        try:
            from PIL import Image
            self.txd.add_texture(Image.open(src), name, fmt)
            self._refresh_list()
            self.listw.setCurrentRow(len(self.txd.textures) - 1)
            self.status.setText(f'added {name} ({fmt})')
        except Exception as e:
            QMessageBox.warning(self, 'Add failed', str(e))

    def _delete(self):
        t = self._cur()
        if not t:
            return
        if QMessageBox.question(self, 'Delete', f"delete '{t.name}'?") != QMessageBox.Yes:
            return
        self.txd.remove_texture(t.name)
        self._refresh_list()
        self.viewport.set_image(None)
        self.status.setText(f'deleted {t.name}')

    def _duplicate(self):
        t = self._cur()
        if not t:
            return
        name, ok = QInputDialog.getText(self, 'Duplicate', 'new name:', text=t.name + '_copy')
        if not ok or not name.strip():
            return
        try:
            self.txd.duplicate_texture(t.name, name)
            self._refresh_list()
            self.listw.setCurrentRow(len(self.txd.textures) - 1)
        except Exception as e:
            QMessageBox.warning(self, 'Duplicate failed', str(e))

    def _gen_mips(self):
        t = self._cur()
        if not t:
            return
        try:
            txdlite.texture_generate_mips(t)
            self._on_select(self.listw.currentRow())
            self.status.setText(f'mip chain regenerated for {t.name} ({t.num_levels} levels)')
        except Exception as e:
            QMessageBox.warning(self, 'Mip gen failed', str(e))

    def _strip_mips(self):
        t = self._cur()
        if not t:
            return
        txdlite.texture_remove_mips(t)
        self._on_select(self.listw.currentRow())
        self.status.setText(f'mips stripped from {t.name}')

    def _quick_edit(self):
        t = self._cur()
        if not t:
            return
        try:
            dlg = PixelEditDialog(self._decoded(t),
                                  f'Quick Edit — {t.name}', self)
            if dlg.exec_() == QDialog.Accepted:
                self.txd.replace(t.name, dlg.result_image())
                self._on_select(self.listw.currentRow())
                self.status.setText(f'edited {t.name} — SAVE TXD to write file')
        except Exception as e:
            QMessageBox.warning(self, 'Edit failed', str(e))

    def _export_one(self):
        t = self._cur()
        if not t:
            return
        out, _ = QFileDialog.getSaveFileName(self, 'Export texture', f'{t.name}.png',
                                             'PNG (*.png)')
        if out:
            txdlite.decode_mip(t).save(out)
            self.status.setText(f'exported {t.name}')


class InspectorScreen(ScreenBase):
    """Map Data Inspector — Ariane Phase 1 port: mod conflict audit."""

    def __init__(self, launcher=None, parent=None):
        super().__init__(parent)
        self.launcher = launcher
        top = QHBoxLayout()
        top.addWidget(heading('MAP DATA INSPECTOR', 24))
        rl = ActionButton('RUN AUDIT')
        rl.clicked.connect(self._run_audit)
        top.addStretch(1)
        top.addWidget(rl)
        self.root.addLayout(top)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setStyleSheet(
            f"QTextEdit {{ background:{T.COLOR_PANEL_BG_LIGHT}; color:{T.COLOR_TEXT_BODY};"
            f"border:1px solid {T.COLOR_DARK_GREEN}; font-family:Consolas; font-size:11px; }}")
        self.root.addWidget(self.details, 1)
        self.status = body('Run the audit to cross-reference every mod DFF against '
                           'loaded TXD sets. Detects unresolved textures, duplicate '
                           'models, and TXD shadow conflicts.')
        self.root.addWidget(self.status)

    def _run_audit(self):
        game = getattr(self.launcher, 'game_path', None) or os.environ.get('GTA_PATH')
        if not game:
            self.status.setText('no game dir known')
            return
        self.status.setText('auditing… (scans every DFF/TXD in modloader)')
        QApplication.processEvents()
        rep = mapdata.audit_mod_textures(game)
        lines = []
        lines.append(f"DFFs scanned:        {rep['dff_count']}")
        lines.append(f"TXD texture names:   {len(rep['txd_names'])}")
        lines.append(f"Unresolved refs:     {len(rep['unresolved'])}")
        lines.append(f"Duplicate DFF names: {sum(1 for v in rep['duplicate_dffs'].values() if len(set(v)) > 1)}")
        lines.append(f"TXD shadow conflicts:{sum(1 for v in rep['txd_shadows'].values() if len(set(v)) > 1)}")
        lines.append('')
        if rep['unresolved']:
            lines.append('== UNRESOLVED TEXTURE REFS (white-model candidates) ==')
            for name, files in sorted(rep['unresolved'].items()):
                lines.append(f"  {name}  <- {files[0]}")
            lines.append('')
        dups = {k: v for k, v in rep['duplicate_dffs'].items() if len(set(v)) > 1}
        if dups:
            lines.append('== DUPLICATE MODELS ACROSS MODS (load-order fights) ==')
            for name, mods in sorted(dups.items()):
                lines.append(f"  {name}: {' vs '.join(sorted(set(mods)))}")
            lines.append('')
        shadows = {k: v for k, v in rep['txd_shadows'].items() if len(set(v)) > 1}
        if shadows:
            lines.append('== TXD SHADOW CONFLICTS (same txd name in multiple mods) ==')
            for name, mods in sorted(shadows.items()):
                lines.append(f"  {name}: {' vs '.join(sorted(set(mods)))}")
        self.details.setPlainText('\n'.join(lines))
        self.status.setText(f"audit complete — {rep['dff_count']} DFFs, "
                            f"{len(rep['unresolved'])} unresolved refs")


class InstallerScreen(ScreenBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.wizard = None
        self.root.addWidget(heading('SAS 1987 INSTALLER WIZARD', 24))
        steps = ("1. Choose mod source (download or existing files)\n"
                 "2. Locate your vanilla San Andreas install\n"
                 "3. Pick destination for the standalone modded install\n"
                 "4. Hash-check gta_sa.exe (+ optional NO-CD downgrade)\n"
                 "5. Copy vanilla files (original untouched)\n"
                 "6. Zip-backup the fresh clone\n"
                 "7. Download main mod + prerequisites\n"
                 "8. Install everything in the right order")
        box = QFrame()
        box.setStyleSheet(f"background:{T.COLOR_PANEL_BG_LIGHT};"
                          f"border:1px solid {T.COLOR_DARK_GREEN};")
        bl = QVBoxLayout(box)
        bl.addWidget(body(steps))
        self.root.addWidget(box)
        self.root.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        go = ActionButton('LAUNCH WIZARD', accent=T.COLOR_SUNSET_ORANGE)
        go.setMinimumSize(200, 48)
        go.clicked.connect(self._launch)
        row.addWidget(go)
        self.root.addLayout(row)

    def _launch(self):
        if self.wizard is None:
            from installer_src.ui.wizard import InstallerWizard  # lazy: needs QApp
            self.wizard = InstallerWizard()
        self.wizard.show()
        self.wizard.raise_()


class WizardScreen(ScreenBase):
    """WIZARD mode page: guide panel + modal launch button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wizard = None
        self.root.addWidget(heading('RUN INSTALL GUIDE', 24))
        steps = ("This guided wizard will set up a standalone\n"
                 "GTA San Andreas Stories 1987 installation.\n\n"
                 "1. Choose mod source (download or existing files)\n"
                 "2. Locate your vanilla San Andreas install\n"
                 "3. Pick destination for the standalone install\n"
                 "4. Hash-check gta_sa.exe (+ optional NO-CD)\n"
                 "5. Copy vanilla files (original untouched)\n"
                 "6. Zip-backup the fresh clone\n"
                 "7. Download main mod + prerequisites\n"
                 "8. Install everything in the right order")
        box = QFrame()
        box.setStyleSheet(f"background:{T.COLOR_PANEL_BG_LIGHT};"
                          f"border:1px solid {T.COLOR_DARK_GREEN};")
        bl = QVBoxLayout(box)
        bl.addWidget(body(steps))
        self.root.addWidget(box)
        self.root.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        go = ActionButton('LAUNCH WIZARD', accent=T.COLOR_SUNSET_ORANGE)
        go.setMinimumSize(200, 48)
        go.clicked.connect(self._launch)
        row.addWidget(go)
        self.root.addLayout(row)

    def _launch(self):
        from installer_src.ui.wizard import InstallerWizard  # lazy import
        wiz = InstallerWizard(self)
        wiz.setWindowModality(Qt.WindowModal)
        wiz.exec_()


# =============================================================================
# Main window
# =============================================================================

class MainWindow(QMainWindow):
    def __init__(self, launcher: GTALauncher):
        super().__init__()
        self.launcher = launcher
        self.setWindowTitle('GTA BRIDGE LAUNCHER')
        self.setMinimumSize(1080, 700)
        self.setStyleSheet(f"background: {T.COLOR_BG};")
        self._aero_applied = False

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # sidebar
        self.side = QWidget()
        self.side.setFixedWidth(210)
        self.side.setStyleSheet(f"background: {T.COLOR_BG}; "
                                f"border-right: 1px solid {T.COLOR_BORDER};")
        self.sv = QVBoxLayout(self.side)
        self.sv.setContentsMargins(10, 18, 10, 14)
        logo = heading('GTA BRIDGE', 20)
        sub = body('LAUNCHER SUITE', dim=True)
        self.sv.addWidget(logo)
        self.sv.addWidget(sub)
        self.sv.addSpacing(18)
        self.nav_buttons: list[NavButton] = []
        self.screens = QStackedWidget()

        # Create all screens (indices: 0=PLAY,1=LIMITS,2=MOD MANAGER,3=TXD EDITOR,
        # 4=INSTALLER,5=WIZARD; INSPECTOR lives inside MOD MANAGER's AUDIT tab)
        all_specs = [('PLAY', lambda: PlayScreen(launcher)),
                     ('LIMITS', lambda: LimitsScreen(launcher)),
                     ('MOD MANAGER', lambda: ModsScreen(launcher)),
                     ('TXD EDITOR', lambda: TxdEditorScreen(launcher)),
                     ('INSTALLER', lambda: InstallerScreen()),
                     ('WIZARD', lambda: WizardScreen())]
        self._screen_specs = all_specs
        for _name, factory in all_specs:
            self.screens.addWidget(factory())

        # nav button container (inserted after subtitle, before stretch)
        self._nav_container = QWidget()
        self._nav_layout = QVBoxLayout(self._nav_container)
        self._nav_layout.setContentsMargins(0, 0, 0, 0)
        self._nav_layout.setSpacing(0)
        self.sv.addWidget(self._nav_container)

        # mode switcher row at bottom of sidebar
        self.sv.addStretch(1)
        self._mode_row = QHBoxLayout()
        self._mode_row.setSpacing(3)
        self._mode_btns: dict[str, QPushButton] = {}
        for label, val in [('WIZARD', 'wizard'), ('SIMPLE', 'simple'), ('ADV', 'adv')]:
            mb = QPushButton(label)
            mb.setCheckable(True)
            mb.setCursor(Qt.PointingHandCursor)
            mb.setMinimumHeight(28)
            mb.setStyleSheet(f"""
                QPushButton {{
                    background: {T.COLOR_PANEL_BG}; color: {T.COLOR_TEXT_DIM};
                    border: 1px solid {T.COLOR_BORDER}; border-radius: 2px;
                    font-size: 10px; padding: 2px 4px;
                }}
                QPushButton:hover {{
                    background: {T.COLOR_HOVER_BG}; color: {T.COLOR_TEXT_BODY};
                }}
                QPushButton:checked {{
                    background: {T.COLOR_WALKMAN_ORANGE}; color: {T.COLOR_ON_ACCENT};
                }}
            """)
            mb.clicked.connect(lambda _, v=val: self._set_mode(v))
            self._mode_btns[val] = mb
            self._mode_row.addWidget(mb)
        self.sv.addLayout(self._mode_row)
        self._mode_hint = body('', dim=True)
        self._mode_hint.setStyleSheet(
            f"color:{T.COLOR_TEXT_DIM}; font-size:9px; padding:0; margin:0;")
        self.sv.addWidget(self._mode_hint)
        ver = body('v2.0.0 — bridge suite', dim=True)
        self.sv.addWidget(ver)
        root.addWidget(self.side)
        root.addWidget(self.screens, 1)

        # apply persisted mode
        mode = launcher.config_manager.get_setting('ui.mode', 'simple')
        self._set_mode(mode, initial=True)

        # first-run SAS87 intro popup (shown after window paint via timer)
        self._sas87_sentinel = _data_dir() / '.sas87_intro_done'
        _sas87_preset = _data_dir() / 'dlc_presets' / 'sas87.json'
        if _sas87_preset.exists() and not self._sas87_sentinel.exists():
            QTimer.singleShot(400, self._show_sas87_intro)

    def _set_mode(self, mode: str, initial: bool = False):
        """Switch UI mode and persist."""
        self.launcher.config_manager.set_setting('ui.mode', mode)
        for val, btn in self._mode_btns.items():
            btn.setChecked(val == mode)
        hints = {'wizard': 'wizard mode', 'simple': '', 'adv': 'advanced'}
        self._mode_hint.setText(hints.get(mode, ''))
        self._rebuild_sidebar(mode)
        if not initial:
            self._nav(0)

    def _rebuild_sidebar(self, mode: str):
        """Clear and rebuild nav buttons based on mode."""
        # clear existing nav buttons
        while self._nav_layout.count():
            it = self._nav_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        self.nav_buttons.clear()

        # define visible screens per mode
        if mode == 'wizard':
            indices = [0, 5]  # PLAY, WIZARD
        elif mode == 'adv':
            indices = [0, 1, 2, 3, 4]  # all except WIZARD (INSPECTOR embedded)
        else:  # simple
            indices = [0, 1, 2, 3, 4]  # all except WIZARD (INSPECTOR embedded)

        for ix in indices:
            name = self._screen_specs[ix][0]
            b = NavButton(name)
            b._screen_ix = ix
            b.clicked.connect(lambda _, i=ix: self._nav(i))
            self._nav_layout.addWidget(b)
            self.nav_buttons.append(b)

    def _nav(self, ix: int):
        for b in self.nav_buttons:
            b.setChecked(getattr(b, '_screen_ix', -1) == ix)
        self.screens.setCurrentIndex(ix)

    def showEvent(self, ev):  # noqa: N802
        super().showEvent(ev)
        # Aero glass + dark titlebar, native frame kept (no frameless chrome).
        # Applied exactly once; pure-ctypes helper no-ops gracefully off-Win10.
        if not self._aero_applied:
            self._aero_applied = True
            try:
                from managers.aero import apply_aero
                apply_aero(int(self.winId()))
            except Exception:
                pass

    def _show_sas87_intro(self):
        """First-run dialog explaining the SAS 87 preloaded modpack."""
        dlg = QDialog(self)
        dlg.setWindowTitle('SAS 1987 — first version')
        dlg.setStyleSheet(f"background:{T.COLOR_BG};")
        dlg.setFixedSize(480, 200)
        lay = QVBoxLayout(dlg)
        msg = QLabel(
            'This build ships with the SAS 87 modpack preloaded. '
            'The launcher will scan for the extra install files; '
            'drop them in launcher_data/dlc_presets/archives/ '
            'or let the launcher download them.')
        msg.setWordWrap(True)
        msg.setStyleSheet(
            f"color:{T.COLOR_TEXT_BODY}; font-size:12px; padding:16px;")
        lay.addWidget(msg)
        btn = QPushButton('GOT IT')
        btn.setStyleSheet(
            f"QPushButton{{background:{T.COLOR_WALKMAN_ORANGE}; color:{T.COLOR_ON_ACCENT};"
            f"border:none; border-radius:2px; padding:6px 24px; font-size:12px;}}"
            f"QPushButton:hover{{background:{T.COLOR_SUNSET_ORANGE};}}")
        btn.clicked.connect(lambda: (self._sas87_sentinel.write_text('1', encoding='utf-8'), dlg.accept()))
        lay.addWidget(btn, 0, Qt.AlignCenter)
        dlg.exec_()

    def closeEvent(self, ev):  # noqa: N802
        ps = self.screens.widget(0)
        if isinstance(ps, PlayScreen) and ps.worker:
            ps.worker.stop()
        super().closeEvent(ev)


def _crash_log(exc: Exception) -> Path:
    log_dir = _data_dir() / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    p = log_dir / f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    import traceback
    p.write_text(traceback.format_exc(), encoding='utf-8')
    return p


def main():
    try:
        _main_inner()
    except Exception as e:
        try:
            log = _crash_log(e)
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, 'GTA Bridge Launcher crashed',
                                 f'{type(e).__name__}: {e}\n\nDetails written to:\n{log}')
        except Exception:
            raise


def _main_inner():
    if os.environ.get('GTA_PATH'):
        game_path = os.environ['GTA_PATH']
    elif (HERE / 'gta_sa.exe').exists():
        game_path = str(HERE)
    else:
        game_path = 'E:/games/gtasa_skygfx_plus'
    db_path = str(F('gta_limits.db'))
    # frozen first-run: provision writable config beside the exe from bundled defaults
    try:
        if not (F('config') / 'settings.json').exists():
            import shutil as _shutil
            _mcfg = Path(getattr(sys, '_MEIPASS', '')) / 'config'
            if (_mcfg / 'settings.json').exists():
                _shutil.copytree(_mcfg, F('config'), dirs_exist_ok=True)
    except Exception:
        pass
    # frozen first-run: preload bundled dlc_presets into writable data dir
    try:
        if getattr(sys, 'frozen', False):
            import shutil as _shutil
            _bundled_presets = Path(getattr(sys, '_MEIPASS', '')) / 'launcher_data' / 'dlc_presets'
            _writable_presets = _data_dir() / 'dlc_presets'
            if _bundled_presets.is_dir():
                if not _writable_presets.is_dir() or not (_writable_presets / 'sas87.json').exists():
                    _writable_presets.mkdir(parents=True, exist_ok=True)
                    _shutil.copytree(_bundled_presets, _writable_presets, dirs_exist_ok=True)
    except Exception:
        pass
    launcher = GTALauncher(game_path=game_path, db_path=db_path,
                           config_path=str(F('config')))
    app = QApplication(sys.argv)
    _resolve_display_font(app)
    # Vista-era typography: Segoe UI 9pt with the default (ClearType) rasterizer.
    _ui_font = QFont('Segoe UI', 9)
    _ui_font.setStyleStrategy(QFont.PreferDefault)
    app.setFont(_ui_font)
    app.setStyleSheet(app_qss())
    win = MainWindow(launcher)
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
