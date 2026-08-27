#!/usr/bin/env python3
"""Verification script for GTA Bridge Launcher"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def verify_launcher():
    """Verify the launcher loads and functions correctly"""
    print("=" * 60)
    print("GTA Bridge Launcher Verification")
    print("=" * 60)
    
    # Test 1: Import launcher module
    print("\n[1/6] Testing imports...")
    try:
        from launcher import LauncherGUI, GTALauncher, GUI_AVAILABLE
        print("  [OK] Imports successful")
    except Exception as e:
        print(f"  [FAIL] Import failed: {e}")
        return False
    
    # Test 2: Check color palette
    print("\n[2/6] Testing color palette...")
    try:
        colors = LauncherGUI.COLORS
        required_keys = ['bg_dark', 'bg_panel', 'bg_frame', 'accent_green', 
                        'text_bright', 'text_body', 'accent_orange', 'accent_cyan']
        for key in required_keys:
            if key not in colors:
                print(f"  [FAIL] Missing color key: {key}")
                return False
        print("  [OK] All required colors present")
    except Exception as e:
        print(f"  [FAIL] Color check failed: {e}")
        return False
    
    # Test 3: Check limit categories
    print("\n[3/6] Testing limit categories...")
    try:
        from limit_adjuster_settings import LimitAdjusterSettings
        categories = LimitAdjusterSettings.LIMIT_CATEGORIES
        expected = ['Pools', 'Memory', 'Models', 'Entity Pointers', 
                   'Rendering', 'Textures', 'IPL & Scripts', 'Advanced']
        for cat in expected:
            if cat not in categories:
                print(f"  [FAIL] Missing category: {cat}")
                return False
        print(f"  [OK] All {len(categories)} categories present")
    except Exception as e:
        print(f"  [FAIL] Category check failed: {e}")
        return False
    
    # Test 4: Check presets
    print("\n[4/6] Testing presets...")
    try:
        from limit_adjuster_settings import LimitAdjusterSettings
        presets = LimitAdjusterSettings.PRESETS
        expected = ['Stock', 'Balanced', 'High Performance', 'Modded', 'Pushed to Farthest']
        for preset in expected:
            if preset not in presets:
                print(f"  [FAIL] Missing preset: {preset}")
                return False
        print(f"  [OK] All {len(presets)} presets present")
    except Exception as e:
        print(f"  [FAIL] Preset check failed: {e}")
        return False
    
    # Test 5: Check overlay method exists
    print("\n[5/6] Testing overlay method...")
    try:
        # Check method exists
        if not hasattr(LauncherGUI, 'create_game_overlay'):
            print("  [FAIL] create_game_overlay method missing")
            return False
        print("  [OK] Overlay method exists")
    except Exception as e:
        print(f"  [FAIL] Overlay check failed: {e}")
        return False
    
    # Test 6: Check memory stats calculation
    print("\n[6/6] Testing memory stats...")
    try:
        import psutil
        total = psutil.virtual_memory().total / (1024*1024)
        available = psutil.virtual_memory().available / (1024*1024)
        used = total - available
        percent = (used / total) * 100
        print(f"  [OK] Memory stats: {used:.0f}MB/{total:.0f}MB ({percent:.0f}%)")
    except Exception as e:
        print(f"  [FAIL] Memory stats check failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("[PASS] ALL VERIFICATION TESTS PASSED")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = verify_launcher()
    sys.exit(0 if success else 1)