import sys, time, subprocess
sys.path.insert(0, "E:/dev(dave)/projects/gta_bridge_launcher")
from pathlib import Path
import bridge_client

# Use GTALauncher's launch_game path (writes ini, deploys asi, Popen)
from launcher import GTALauncher

game_dir = "E:/games/gtasa_skygfx_plus"
launcher = GTALauncher(game_path=game_dir, db_path=f"{game_dir}/gta_limits.db", config_path=f"{game_dir}/config")
print(f"game_path={launcher.game_path} exists={launcher.game_path.exists()}")
print(f"selected_exe before={launcher.selected_exe}")
# ensure any old ini/asi are fresh
ini = launcher.write_bridge_ini()
print(f"write_bridge_ini -> {ini} exists={Path(ini).exists()}")
if Path(ini).exists():
    print(open(ini).read().strip())
deployed, dest = launcher.deploy_asi()
print(f"deploy_asi -> {deployed} {dest}")

# kill any stale game
import psutil
for p in psutil.process_iter(['name','pid']):
    if p.info['name'] and 'gta_sa' in p.info['name'].lower():
        print(f"killing stale {p.info}")
        try: p.kill()
        except: pass
time.sleep(1)

print("\n=== launching via GTALauncher.launch_game ===")
proc = launcher.launch_game('gtasa')
print(f"launched PID {proc.pid}")

c = bridge_client.GBridgeClient()
ok = c.wait_for_pipe(timeout_s=15)
print(f"wait_for_pipe={ok}")
if not ok:
    proc.terminate()
    sys.exit(1)
ok = c.connect()
print(f"connect={ok} err? {c.is_connected()}")
print("HELLO", c.hello())
print("PING", c.ping())
print("STATUS", c.status())
print("MEM", c.mem())
# poll pools a few times, wait for game to init
for i in range(8):
    time.sleep(1.5)
    pools = {}
    for name in ['Peds','Vehicles','Buildings','Objects','Dummys','ColModel']:
        pools[name]=c.usage(name)
    print(f"[{i}] pools={pools} mem={c.mem()}")
    if any(v[0]>=0 for v in pools.values()):
        print("Got valid pool usage!")
        break

# also test BridgeMonitor callback a bit
print("\n=== BridgeMonitor 5s ===")
from bridge_client import BridgeMonitor
stats_list=[]
def cb(s):
    stats_list.append(s)
    print(f" cb connected={s['connected']} mem={s.get('mem_avail')}/{s.get('mem_used')} pools={s.get('pools')}")
mon = BridgeMonitor(callback=cb, poll_interval=1.0)
mon.start()
time.sleep(6)
mon.stop()
mon.join(timeout=3)
print(f"collected {len(stats_list)} callbacks")

c.close()
time.sleep(0.5)
try:
    proc.terminate()
    proc.wait(timeout=5)
    print(f"game terminated exit {proc.returncode}")
except Exception as e:
    print(e)
    try: proc.kill()
    except: pass
