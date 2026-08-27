"""
sweep_harness.py — LOD / streaming sweep CLI for GTA Bridge Launcher.

Usage:
    python -m utils.sweep_harness --game-dir <path> --sweep-id <id>
"""

import configparser
import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

BASE: Dict[str, object] = {
    'streaming_mem_mb': 2048,
    'max_lod_scale': 4.0,
    'vegetation_boost': 1,
}

CANDIDATES: List[Tuple[str, Dict[str, object]]] = [
    ('c1_stock',       {'max_lod_scale': 4.0}),
    ('c2_lod6',        {'max_lod_scale': 6.0}),
    ('c3_lod6_noveg',  {'max_lod_scale': 6.0, 'vegetation_boost': 0}),
    ('c4_perf',        {'max_lod_scale': 2.0, 'streaming_mem_mb': 1024}),
]

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def apply_candidate(game_dir: str, candidate_id: str,
                    overrides: Dict[str, object]) -> str:
    """Read <game_dir>/gta_bridge.ini preserving [PROFILES], rewrite [BRIDGE]
    = BASE merged with *overrides*, write as ASCII, return ini path."""
    ini = Path(game_dir) / 'gta_bridge.ini'
    cp = configparser.ConfigParser()
    cp.optionxform = str  # preserve case

    if ini.exists():
        try:
            cp.read(str(ini), encoding='utf-8')
        except configparser.Error:
            cp = configparser.ConfigParser()
            cp.optionxform = str

    # Build merged [BRIDGE] values
    merged = dict(BASE)
    merged.update(overrides)

    # Ensure [BRIDGE] section exists and write merged values
    if not cp.has_section('BRIDGE'):
        cp.add_section('BRIDGE')
    for k, v in merged.items():
        cp.set('BRIDGE', k, str(v))

    # Ensure [PROFILES] is present (preserved from original or created)
    if not cp.has_section('PROFILES'):
        cp.add_section('PROFILES')

    with open(str(ini), 'w', encoding='ascii') as f:
        cp.write(f)

    return str(ini)


def parse_rows(text: str) -> List[Dict[str, float]]:
    """Parse whitespace/comma 4-column lines 'area lo av hi' into list of
    dicts with keys 'area' (str), 'min', 'avg', 'max' (float)."""
    rows: List[Dict[str, float]] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # split on whitespace or comma
        parts = line.replace(',', ' ').split()
        if len(parts) < 4:
            continue
        area = parts[0]
        try:
            lo = float(parts[1])
            av = float(parts[2])
            hi = float(parts[3])
        except ValueError:
            continue
        rows.append({'area': area, 'min': lo, 'avg': av, 'max': hi})
    return rows


def winner_rank(rows: List[Dict[str, float]]) -> float:
    """Harmonic mean of per-area avgs; *0.75 penalty if any min < 25.0;
    rounded to 2 decimal places."""
    if not rows:
        return 0.0
    avgs = [r['avg'] for r in rows]
    # harmonic mean
    inv_sum = sum(1.0 / a for a in avgs if a != 0.0)
    if inv_sum == 0.0:
        return 0.0
    hmean = len(avgs) / inv_sum
    # penalty
    if any(r['min'] < 25.0 for r in rows):
        hmean *= 0.75
    return round(hmean, 2)


def append_csv(sweep_id: str, candidate_id: str,
               rows: List[Dict[str, float]]) -> Path:
    """Write launcher_data/logs/sweep_<sweep_id>.csv with rows containing
    candidate_id, area, min, avg, max. Returns the Path written."""
    log_dir = Path('launcher_data') / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    out = log_dir / f'sweep_{sweep_id}.csv'
    exists = out.exists()
    with open(str(out), 'a', newline='', encoding='ascii') as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(['candidate_id', 'area', 'min', 'avg', 'max'])
        for r in rows:
            w.writerow([candidate_id, r['area'], r['min'], r['avg'], r['max']])
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description='LOD/streaming sweep harness')
    ap.add_argument('--game-dir', required=True)
    ap.add_argument('--sweep-id', required=True)
    args = ap.parse_args()

    game_dir = args.game_dir
    sweep_id = args.sweep_id

    best_rank = -1.0
    best_candidate = None

    for cid, overrides in CANDIDATES:
        ini_path = apply_candidate(game_dir, cid, overrides)
        print(f'[sweep] candidate={cid} ini={ini_path}')
        print('[sweep] paste rows (area min avg max), then type DONE on a line by itself:')

        lines: List[str] = []
        while True:
            try:
                raw = sys.stdin.readline()
            except KeyboardInterrupt:
                raw = ''
            if not raw:
                break
            raw = raw.strip()
            if raw.upper() == 'DONE' or raw.upper() == '':
                break
            lines.append(raw)

        text = '\n'.join(lines)
        rows = parse_rows(text)
        if not rows:
            print(f'[sweep] no valid rows for {cid}, skipping')
            continue

        rank = winner_rank(rows)
        print(f'[sweep] rank={rank}')

        csv_path = append_csv(sweep_id, cid, rows)
        print(f'[sweep] csv={csv_path}')

        if rank > best_rank:
            best_rank = rank
            best_candidate = cid

    if best_candidate is not None:
        print(f'WINNER candidate={best_candidate} rank={best_rank}')
    else:
        print('WINNER none')


if __name__ == '__main__':
    main()