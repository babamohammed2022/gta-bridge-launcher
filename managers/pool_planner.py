"""
Pool Planner - Memory pool recommendations based on hardware
"""

TARGETS = {
    'balanced': {'sf': .30, 'tf': .40, 'mf': .20, 'sc': 2048, 'tc': 1024, 'mc': 512, 'lod': 4.0},
    'quality':  {'sf': .40, 'tf': .50, 'mf': .25, 'sc': 2048, 'tc': 1536, 'mc': 768, 'lod': 6.0},
    'perf':     {'sf': .20, 'tf': .30, 'mf': .15, 'sc': 1024, 'tc': 512,  'mc': 256, 'lod': 2.0},
}


def recommended_pools(vram_mb, ram_mb, target='balanced'):
    """Return recommended pool sizes given VRAM and system RAM in MB."""
    t = TARGETS[target]
    vram_mb = max(256, int(vram_mb))
    ram_mb = max(512, int(ram_mb))
    return {
        'streaming': min(int(vram_mb * t['sf']), t['sc'], int(ram_mb * 0.3)),
        'textures':  min(int(vram_mb * t['tf']), t['tc']),
        'models':    min(int(vram_mb * t['mf']), t['mc']),
        'max_lod_scale': round(t['lod'] if vram_mb >= 1024 else min(t['lod'], 3.0), 1),
    }