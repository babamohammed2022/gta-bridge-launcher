#!/usr/bin/env python3
"""
test_bridge_sim.py - End-to-end test of bridge_client against a FAKE gta_bridge.asi.

Spins up a named-pipe server (ctypes, same name the real ASI uses) that speaks
the documented protocol, then drives GBridgeClient + BridgeMonitor against it.
ASCII-only console output (cp1252-safe).
"""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Surface bridge_client internal logs (connect failures etc.)
import logging
logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')

import ctypes
from ctypes import wintypes

PIPE_NAME = r'\\.\pipe\gta_bridge'
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
PIPE_ACCESS_DUPLEX = 3
PIPE_TYPE_MESSAGE = 4
PIPE_READMODE_MESSAGE = 2
ERROR_BROKEN_PIPE = 109
ERROR_NO_DATA = 232

k32 = ctypes.windll.kernel32


def create_pipe():
    handle = k32.CreateNamedPipeW(
        PIPE_NAME,
        PIPE_ACCESS_DUPLEX,
        PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE,
        1,          # max instances
        4096,       # out buffer
        4096,       # in buffer
        0, None)
    if handle == INVALID_HANDLE_VALUE:
        raise OSError(f"CreateNamedPipeW failed: {k32.GetLastError()}")
    return handle


def read_line(handle):
    """Read bytes until newline. Returns str or None on broken pipe."""
    buf = ctypes.create_string_buffer(4096)
    data = b''
    while b'\n' not in data:
        got = wintypes.DWORD(0)
        ok = k32.ReadFile(handle, buf, 4096, ctypes.byref(got), None)
        if not ok or got.value == 0:
            err = k32.GetLastError()
            if err in (ERROR_BROKEN_PIPE, ERROR_NO_DATA):
                return None
            return None
        data += buf.raw[:got.value]
    return data.decode('ascii', errors='replace').strip()


def write_line(handle, text):
    payload = (text + '\n').encode('ascii')
    wrote = wintypes.DWORD(0)
    ok = k32.WriteFile(handle, payload, len(payload), ctypes.byref(wrote), None)
    return bool(ok)


POOL_STATE = {'Peds': (57, 350), 'Vehicles': (31, 200), 'Buildings': (9000, 16000)}
MEM_STATE = (1834, 206)   # avail_mb, used_mb


def serve_once(handle):
    """Handle one client connection until broken."""
    while True:
        line = read_line(handle)
        if line is None:
            return False
        if line == 'HELLO':
            write_line(handle, 'OK GTABRIDGE 1.0')
        elif line == 'PING':
            write_line(handle, 'PONG')
        elif line == 'STATUS':
            write_line(handle, 'STATUS alive')
        elif line == 'MEM':
            write_line(handle, f'MEM {MEM_STATE[0]} {MEM_STATE[1]}')
        elif line.startswith('USAGE '):
            name = line.split(None, 1)[1]
            u, m = POOL_STATE.get(name, (-1, -1))
            write_line(handle, f'USAGE {name} {u} {m}')
        else:
            write_line(handle, 'ERR unknown')


def fake_asi_server(stop_event):
    """Server loop: create/connect/serve/recreate until stopped."""
    while not stop_event.is_set():
        handle = create_pipe()
        connected = k32.ConnectNamedPipe(handle, None)
        if not connected and k32.GetLastError() != 535:  # 535 = ERROR_PIPE_CONNECTED
            k32.CloseHandle(handle)
            continue
        try:
            while not stop_event.is_set():
                if not serve_once(handle):
                    break
        finally:
            k32.DisconnectNamedPipe(handle)
            k32.CloseHandle(handle)
    print("[SIM] server exited")


def main():
    results = []

    def check(label, ok):
        results.append(ok)
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")

    print("=" * 60)
    print("Bridge IPC Simulation Test")
    print("=" * 60)

    stop_event = threading.Event()
    server = threading.Thread(target=fake_asi_server, args=(stop_event,), daemon=True)
    server.start()
    time.sleep(0.3)

    # --- Test 1: GBridgeClient direct ---
    print("\n[1/3] GBridgeClient direct commands")
    from bridge_client import GBridgeClient
    c = GBridgeClient()
    check("wait_for_pipe", c.wait_for_pipe(timeout_s=5))
    check("connect", c.connect())
    check("hello == GTABRIDGE 1.0", c.hello() == 'GTABRIDGE 1.0')
    check("ping", c.ping())
    check("status == alive", c.status() == 'alive')
    mem = c.mem()
    check(f"mem == {MEM_STATE}", mem == MEM_STATE)
    u = c.usage('Peds')
    check(f"usage Peds == {POOL_STATE['Peds']}", u == POOL_STATE['Peds'])
    u = c.usage('UnknownPool')
    check("usage Unknown == (-1,-1)", u == (-1, -1))

    # --- Test 2: parsing edge cases ---
    print("\n[2/3] Parsing robustness")
    check("mem returns tuple of ints",
          isinstance(mem, tuple) and all(isinstance(x, int) for x in mem))
    c.close()
    check("close then cmd -> None", c._cmd('PING') is None)

    # --- Test 3: BridgeMonitor callback flow ---
    print("\n[3/3] BridgeMonitor live polling")
    from bridge_client import BridgeMonitor
    received = []
    done = threading.Event()

    def cb(stats):
        received.append(stats)
        if stats.get('connected') and stats.get('pools', {}).get('Peds', (-1, -1))[0] >= 0:
            done.set()

    mon = BridgeMonitor(callback=cb, pools=list(POOL_STATE.keys()),
                        poll_interval=0.5, connect_timeout=5)
    mon.start()
    ok = done.wait(10)
    check("monitor reported connected stats with pool usage", ok)
    if received:
        last = [s for s in received if s.get('connected')]
        if last:
            s = last[-1]
            check(f"mem_avail == {MEM_STATE[0]}", s['mem_avail'] == MEM_STATE[0])
            check("pools dict populated", len(s['pools']) == len(POOL_STATE))
    mon.stop()
    mon.join(timeout=5)
    check("monitor thread exits cleanly", not mon.is_alive())

    stop_event.set()
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    status = "PASS" if passed == total else "FAIL"
    print(f"[{status}] {passed}/{total} checks passed")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
