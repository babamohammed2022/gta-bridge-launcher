import sys
sys.path.insert(0, '.')
from managers import mapdata, txdlite
from pathlib import Path

game = Path('E:/games/gtasa_skygfx_plus')
want = {'vehiclegeneric256', 'vehiclelights128', 'vehiclegrunge256',
        'vehicledash32', 'pinelo128', 'lod_largefurs07', 'veg_largefurs05',
        'kb_teracota_pot2_64', 'des_motelwall3', 'jlneona'}
found = {}
n = 0
for img in ['models/gta3.img', 'models/player.img', 'models/gta_int.img']:
    p = game / img
    entries = mapdata.read_img_entries(str(p))
    with open(str(p), 'rb') as fh:
        for name, off, size in entries:
            if not name.endswith('.txd'):
                continue
            n += 1
            try:
                fh.seek(off)
                t = txdlite.TxdFile.loads(fh.read(size))
                for x in t.textures:
                    xn = str(getattr(x, 'name', '')).lower()
                    if xn in want:
                        found.setdefault(xn, []).append(name)
            except Exception:
                pass
print('txds scanned:', n)
for k in sorted(want):
    print(' ', k, '->', found.get(k))
