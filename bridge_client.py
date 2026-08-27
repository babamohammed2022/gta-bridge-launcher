#!/usr/bin/env python3
"""
bridge_client.py - Named-pipe IPC client for the gta_bridge ASI agent.

MMO-launcher-style monitoring: the launcher connects to a named pipe exposed
by the C++ ASI inside the running game and polls live usage stats.

Protocol (line-based, ASCII):
    "HELLO"          -> "OK GTABRIDGE 1.0"
    "PING"           -> "PONG"
    "STATUS"         -> "STATUS alive"
    "MEM"            -> "MEM <avail_mb> <used_mb>"
    "USAGE <name>"   -> "USAGE <name> <used> <max>"  (or "<name> -1 -1")

Stdlib only. Safe defaults on any IO error so the launcher never crashes
because the bridge is down.
"""

import os
import threading
import time
import logging

logger = logging.getLogger(__name__)

PIPE_NAME = r'\\.\pipe\gta_bridge'

# Pool names polled by default when a monitor is started without an explicit list
DEFAULT_POOLS = ['Peds', 'Vehicles', 'Buildings', 'Objects', 'Dummys']


class GBridgeClient:
    """Thread-safe client for the gta_bridge named pipe."""

    def __init__(self, pipe_name: str = PIPE_NAME):
        self.pipe_name = pipe_name
        self._lock = threading.Lock()
        self._fh = None

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #
    def wait_for_pipe(self, timeout_s: float = 30.0, poll_s: float = 0.5) -> bool:
        """Poll until the pipe exists (ASI created it) or timeout expires."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if os.path.exists(self.pipe_name):
                return True
            time.sleep(poll_s)
        return False

    def connect(self, retries: int = 6, delay_s: float = 0.25) -> bool:
        """Open the pipe, retrying through transient states.

        A freshly-created or just-disconnected pipe instance can briefly
        reject opens with EINVAL/ENOENT even though os.path.exists() is
        True - retrying is required (same as real MMO launchers polling
        the game process).
        """
        for attempt in range(max(1, retries)):
            with self._lock:
                if self._fh is not None:
                    return True
                try:
                    self._fh = open(self.pipe_name, 'r+b', buffering=0)
                    return True
                except OSError as e:
                    logger.debug(
                        f"bridge connect attempt {attempt + 1}/{retries} "
                        f"failed: {type(e).__name__}: {e}")
                    self._fh = None
            time.sleep(delay_s)
        logger.warning(f"bridge connect failed after {retries} attempts")
        return False

    def close(self):
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None

    def is_connected(self) -> bool:
        return self._fh is not None

    # ------------------------------------------------------------------ #
    # Command IO
    # ------------------------------------------------------------------ #
    def _cmd(self, line: str):
        """Send one command line, return response string or None on failure."""
        with self._lock:
            if self._fh is None:
                return None
            try:
                self._fh.write((line + '\n').encode('ascii'))
                raw = self._fh.readline()
                if not raw:
                    # Pipe closed by peer
                    self._fh.close()
                    self._fh = None
                    return None
                return raw.decode('ascii', errors='replace').strip()
            except (OSError, ValueError) as e:
                logger.debug(f"bridge cmd '{line}' failed: {e}")
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None
                return None

    # ------------------------------------------------------------------ #
    # Typed commands
    # ------------------------------------------------------------------ #
    def hello(self):
        """Returns version string like 'GTABRIDGE 1.0' or None."""
        r = self._cmd('HELLO')
        if r and r.startswith('OK '):
            return r[3:]
        return None

    def ping(self) -> bool:
        return self._cmd('PING') == 'PONG'

    def status(self):
        r = self._cmd('STATUS')
        if r and r.startswith('STATUS '):
            return r[len('STATUS '):]
        return None

    def mem(self):
        """Returns (avail_mb, used_mb) or None."""
        r = self._cmd('MEM')
        if r and r.startswith('MEM '):
            parts = r.split()
            if len(parts) >= 3:
                try:
                    return int(parts[1]), int(parts[2])
                except ValueError:
                    pass
        return None

    def usage(self, name: str):
        """Returns (used, max) ints, or (-1, -1) when unknown, None on IO error."""
        r = self._cmd(f'USAGE {name}')
        if r is None:
            return None
        parts = r.split()
        # Expect: USAGE <name> <used> <max>
        if len(parts) >= 4 and parts[0] == 'USAGE':
            try:
                return int(parts[2]), int(parts[3])
            except ValueError:
                return (-1, -1)
        return (-1, -1)

    # ---- Mirage Pool v1: shared-memory transport ----

    def shm_open(self, size_mb: int):
        """Ask bridge to map the launcher-created 'GTA_BRIDGE_SHM' section."""
        r = self._cmd(f'SHM_OPEN {size_mb}')
        if r and r.startswith('OK'):
            return True
        return False

    def shm_read(self, offset: int, length: int):
        """Read bytes back from the shared view via pipe (hex). Returns bytes or None."""
        r = self._cmd(f'SHM_READ {offset} {length}')
        if r and r.startswith('OK SHMREAD '):
            try:
                return bytes.fromhex(r[len('OK SHMREAD '):].strip())
            except ValueError:
                return None
        return None

    def shm_stat(self):
        """Returns (handle, view, size) strings or None."""
        r = self._cmd('SHM_STAT')
        if r and r.startswith('SHMSTAT '):
            return tuple(r[len('SHMSTAT '):].split())
        return None


def create_shared_section(size_mb: int = 256, name: str = 'GTA_BRIDGE_SHM'):
    """Launcher-side (64-bit): create the named page-file-backed section + map a view.

    Returns ((handle, view_addr, size), None) on success or (None, error_str).
    """
    import ctypes
    k32 = ctypes.windll.kernel32
    PAGE_READWRITE = 0x04
    FILE_MAP_ALL_ACCESS = 0xF001F
    size = size_mb * 1024 * 1024
    h = k32.CreateFileMappingW(ctypes.c_void_p(-1), None, PAGE_READWRITE,
                               (size >> 32) & 0xFFFFFFFF, size & 0xFFFFFFFF, name)
    if not h:
        return None, f'CreateFileMapping failed err={k32.GetLastError()}'
    view = k32.MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, size)
    if not view:
        k32.CloseHandle(h)
        return None, f'MapViewOfFile failed err={k32.GetLastError()}'
    return (h, view, size), None


def shm_write(view_addr: int, offset: int, data: bytes):
    """Write bytes into the mapped view (launcher side)."""
    import ctypes
    ctypes.memmove(view_addr + offset, data, len(data))


class BridgeMonitor(threading.Thread):
    """Daemon thread polling the bridge and pushing stats to a callback.

    Callback signature: callback(dict | None)
        dict: {'connected': bool, 'mem_avail': int, 'mem_used': int,
               'pools': {name: (used, max)}}
        None is never passed; disconnection is reported as connected=False.
    """

    def __init__(self, callback, pools=None, poll_interval=1.0,
                 reconnect_interval=2.0, connect_timeout=20.0):
        super().__init__(daemon=True, name='BridgeMonitor')
        self.client = GBridgeClient()
        self.callback = callback
        self.pools = list(pools) if pools else list(DEFAULT_POOLS)
        self.poll_interval = poll_interval
        self.reconnect_interval = reconnect_interval
        self.connect_timeout = connect_timeout
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        logger.info("BridgeMonitor: starting")
        while not self.stop_event.is_set():
            # --- connect phase ---
            if not self.client.is_connected():
                if not self.client.wait_for_pipe(
                        timeout_s=self.connect_timeout, poll_s=0.5):
                    self._report(connected=False)
                    self.stop_event.wait(self.reconnect_interval)
                    continue
                if not self.client.connect():
                    self._report(connected=False)
                    self.stop_event.wait(self.reconnect_interval)
                    continue
                ver = self.client.hello()
                logger.info(f"BridgeMonitor: connected ({ver})")

            # --- poll phase ---
            mem = self.client.mem()
            pools = {}
            for name in self.pools:
                u = self.client.usage(name)
                pools[name] = u if u is not None else (-1, -1)

            if mem is None:
                # Pipe lost this cycle
                self._report(connected=False)
                self.client.close()
                self.stop_event.wait(self.reconnect_interval)
                continue

            self._report(connected=True, mem_avail=mem[0], mem_used=mem[1],
                         pools=pools)
            self.stop_event.wait(self.poll_interval)

        self.client.close()
        logger.info("BridgeMonitor: stopped")

    def _report(self, **kw):
        stats = {'connected': kw.get('connected', False),
                 'mem_avail': kw.get('mem_avail', -1),
                 'mem_used': kw.get('mem_used', -1),
                 'pools': kw.get('pools', {})}
        try:
            self.callback(stats)
        except Exception as e:  # callback must never kill the thread
            logger.debug(f"BridgeMonitor callback error: {e}")
