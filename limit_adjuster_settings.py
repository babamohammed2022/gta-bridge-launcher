"""
Limit Adjuster Settings Panel - Vista Aero themed scroll window with MMO-style launcher experience
"""

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:  # frozen PyQt5 build has no tkinter; data (PRESETS/LIMIT_CATEGORIES) still loads
    tk = None
    ttk = None
    messagebox = None
from typing import Dict, List, Any, Optional
from pathlib import Path
import json


class LimitAdjusterSettings:
    """Manages limit adjuster settings with Vista Aero styling"""
    
    # SAS 87 installer + launcher synthwave palette (yellow base, VCS accents)
    COLORS = {
        # SAS 87 yellow base
        'bg_yellow': '#FFE600',
        'bg_yellow_light': '#FFF9C4',
        'bg_yellow_dark': '#FFD600',
        'bg_gradient_top': '#FFE600',
        'bg_gradient_bottom': '#FFD600',
        'frame_bg': '#FFFDE7',
        'frame_border': '#FFD54F',
        'title_blue': '#0a1f12',
        'button_bg_top': '#3d8a3d',
        'button_bg_mid': '#0a1f12',
        'button_bg_bottom': '#0d3b1f',
        'button_hover': '#FFF176',
        'button_pressed': '#FFD54F',
        'play_button': '#3d8a3d',
        'play_button_hover': '#5fc45f',
        'text_primary': '#0a1f12',
        'text_secondary': '#3d1f00',
        'text_disabled': '#8a7a00',
        'status_bg': '#FFF9C4',
        'category_header': '#FFECB3',
        'preset_button': '#3d8a3d',
        'preset_button_hover': '#ff6a2b',
        # launcher synthwave accents retained
        'bg_dark': '#0a1f12',
        'bg_panel': '#0a1f12',
        'bg_frame': '#0d3b1f',
        'panel_bg_light': '#15351f',
        'accent_green': '#3d8a3d',
        'accent_green_light': '#5fc45f',
        'accent_orange': '#ff6a2b',
        'accent_pink': '#ff2bd6',
        'accent_cyan': '#00f0ff',
        'text_bright': '#0a1f12',
        'text_body': '#0a1f12',
        'text_dim': '#5d4e00',
        'border_light': '#ff6a2b',
        'border_dark': '#0d3b1f',
        'highlight': '#ff6a2b',
        'glass_border': '#FFD54F',
        'success': '#3d8a3d',
        'danger': '#ff5b5b',
    }
    
    # Limit categories and their settings — maxima quadrupled for Top of 2007 vegetation/mesh pools (b16)
    LIMIT_CATEGORIES = {
        'Pools': {
            'icon': '📦',
            'settings': [
                {'name': 'Peds', 'type': 'int', 'default': 240, 'max': 255, 'description': 'Maximum pedestrians'},
                {'name': 'Vehicles', 'type': 'int', 'default': 230, 'max': 255, 'description': 'Maximum vehicles'},
                {'name': 'Buildings', 'type': 'int', 'default': 150000, 'max': 4000000, 'description': 'Building pool size (quadrupled mesh)'},
                {'name': 'Objects', 'type': 'int', 'default': 60000, 'max': 400000, 'description': 'Dynamic objects (quadrupled vegetation)'},
                {'name': 'Dummys', 'type': 'int', 'default': 150000, 'max': 2000000, 'description': 'Dummy objects (quadrupled)'},
                {'name': 'ColModel', 'type': 'int', 'default': 42000, 'max': 400000, 'description': 'Collision models (quadrupled mesh)'},
                {'name': 'PedIntelligence', 'type': 'int', 'default': 240, 'max': 255, 'description': 'Ped AI instances'},
            ]
        },
        'Entity Pointers': {
            'icon': '🔗',
            'settings': [
                {'name': 'PtrNodeSingle', 'type': 'int', 'default': 300000, 'max': 4000000, 'description': 'Single linked list nodes (quadrupled)'},
                {'name': 'PtrNodeDouble', 'type': 'int', 'default': 300000, 'max': 4000000, 'description': 'Double linked list nodes (quadrupled)'},
                {'name': 'PtrNode', 'type': 'int', 'default': 300000, 'max': 4000000, 'description': 'Pointer nodes (quadrupled)'},
                {'name': 'EntryInfoNode', 'type': 'int', 'default': 3200, 'max': 200000, 'description': 'Collidable entity info nodes (quadrupled)'},
                {'name': 'VisibleEntityPtrs', 'type': 'int', 'default': 300000, 'max': 2000000, 'description': 'Visible non-LOD entities (quadrupled)'},
                {'name': 'VisibleLodPtrs', 'type': 'int', 'default': 600000, 'max': 2000000, 'description': 'Visible LOD entities (quadrupled)'},
                {'name': 'AlphaEntityList', 'type': 'int', 'default': 8000, 'max': 200000, 'description': 'Alpha entity list (quadrupled)'},
            ]
        },
        'Memory': {
            'icon': '💾',
            'settings': [
                {'name': 'StreamingInfo', 'type': 'int', 'default': 18000, 'max': 200000, 'description': 'Streaming info array size (quadrupled)'},
                {'name': 'MemoryAvailable', 'type': 'str', 'default': '30%', 'options': ['10%', '20%', '30%', '40%', '50%', '60%', '70%', '80%', '32', '64', '128', '256', '512', '1024', '2048', '4096', '8192', 'unlimited'], 'description': 'Streaming memory available (auto 1/4 RAM, 32-8192 period)'},
                {'name': 'ExtraObjectsDir', 'type': 'int', 'default': 1536, 'max': 8192, 'description': 'Extra objects directory size (quadrupled)'},
                {'name': 'VRAM', 'type': 'int', 'default': 512, 'max': 8192, 'description': 'Video memory guarantee MB auto 1/4 RAM 512-8192'},
            ]
        },
        'Models': {
            'icon': '🧩',
            'settings': [
                {'name': 'AtomicModels', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Non-breakable object definitions (quadrupled mesh)'},
                {'name': 'DamageAtomicModels', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Breakable object definitions (quadrupled)'},
                {'name': 'TimeModels', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Timed object definitions (quadrupled)'},
                {'name': 'ClumpModels', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Hierarchical object definitions (quadrupled)'},
                {'name': 'VehicleModels', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Vehicle definitions (quadrupled)'},
                {'name': 'PedModels', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Pedestrian definitions (quadrupled)'},
                {'name': 'WeaponModels', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Weapon definitions (quadrupled)'},
            ]
        },
        'Rendering': {
            'icon': '🎨',
            'settings': [
                {'name': 'StaticShadows', 'type': 'int', 'default': 2048, 'max': 65536, 'description': 'Static shadows (quadrupled)'},
                {'name': 'Coronas', 'type': 'int', 'default': 20000, 'max': 800000, 'description': 'Light coronas (quadrupled)'},
                {'name': 'ScriptSearchLights', 'type': 'int', 'default': 1024, 'max': 40000, 'description': 'Script searchlights (quadrupled)'},
                {'name': 'OutsideWorldWaterBlocks', 'type': 'int', 'default': 500, 'max': 20000, 'description': 'Water blocks outside world (quadrupled)'},
                {'name': 'StreamingObjectInstancesList', 'type': 'int', 'default': 30000, 'max': 800000, 'description': 'Streamed object instances (quadrupled)'},
            ]
        },
        'Textures': {
            'icon': '🖼️',
            'settings': [
                {'name': 'TxdStore', 'type': 'int', 'default': 1385, 'max': 20000, 'description': 'Texture dictionary pool (quadrupled vegetation)'},
                {'name': 'AudioScriptObj', 'type': 'int', 'default': 192, 'max': 4000, 'description': 'Script sound objects (quadrupled)'},
                {'name': '2dEffects', 'type': 'int', 'default': 0, 'max': 4000, 'description': '2D effects (quadrupled)'},
            ]
        },
        'IPL & Scripts': {
            'icon': '📄',
            'settings': [
                {'name': 'EntitiesPerIpl', 'type': 'int', 'default': 1000, 'max': 40000, 'description': 'Entities per IPL file (quadrupled)'},
                {'name': 'EntityIpl', 'type': 'int', 'default': 100, 'max': 4000, 'description': 'Number of IPL files (quadrupled)'},
                {'name': 'PointRoute', 'type': 'int', 'default': 1000, 'max': 40000, 'description': 'AI point routes (quadrupled)'},
                {'name': 'PatrolRoute', 'type': 'int', 'default': 1000, 'max': 40000, 'description': 'AI patrol routes (quadrupled)'},
                {'name': 'NodeRoute', 'type': 'int', 'default': 1000, 'max': 40000, 'description': 'Dynamic AI routes (quadrupled)'},
                {'name': 'Task', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Pedestrian tasks (quadrupled)'},
                {'name': 'Event', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Event notifications (quadrupled)'},
            ]
        },
        'Advanced': {
            'icon': '⚙️',
            'settings': [
                {'name': 'TaskAllocator', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Task allocator (quadrupled)'},
                {'name': 'PedAttractors', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Ped attractors (quadrupled)'},
                {'name': 'VehicleStructs', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Vehicle model info (quadrupled)'},
                {'name': 'MatrixList', 'type': 'int', 'default': 10000, 'max': 400000, 'description': 'Transformation matrices (quadrupled)'},
                {'name': 'Treadables', 'type': 'int', 'default': 1, 'max': 400, 'description': 'Animated buildings (quadrupled vegetation)'},
                {'name': 'CollisionSize', 'type': 'int', 'default': 1024, 'max': 40000, 'description': 'Collision model size KB (quadrupled)'},
            ]
        }
    }
    
    # Preset configurations
    PRESETS = {
        'Stock': {
            'Peds': 140, 'Vehicles': 110, 'Buildings': 100000, 'Objects': 10000,
            'Dummys': 50000, 'ColModel': 15000, 'PedIntelligence': 140,
            'StreamingInfo': 6350, 'MemoryAvailable': '30%', 'ExtraObjectsDir': 512,
            'AtomicModels': 10000, 'DamageAtomicModels': 10000, 'TimeModels': 10000,
            'ClumpModels': 10000, 'VehicleModels': 10000, 'PedModels': 10000, 'WeaponModels': 10000,
            'PtrNodeSingle': 300000, 'PtrNodeDouble': 300000, 'PtrNode': 300000,
            'EntryInfoNode': 3200, 'VisibleEntityPtrs': 100000, 'VisibleLodPtrs': 100000, 'AlphaEntityList': 2000,
            'StaticShadows': 2048, 'Coronas': 20000, 'ScriptSearchLights': 1024,
            'OutsideWorldWaterBlocks': 500, 'StreamingObjectInstancesList': 30000,
            'TxdStore': 1385, 'AudioScriptObj': 192, '2dEffects': 0,
            'EntitiesPerIpl': 1000, 'EntityIpl': 100, 'PointRoute': 1000,
            'PatrolRoute': 1000, 'NodeRoute': 1000, 'Task': 10000, 'Event': 10000,
            'TaskAllocator': 10000, 'PedAttractors': 10000, 'VehicleStructs': 10000,
            'MatrixList': 10000, 'Treadables': 1, 'CollisionSize': 1024
        },
        'Balanced': {
            'Peds': 140, 'Vehicles': 110, 'Buildings': 100000, 'Objects': 10000,
            'MemoryAvailable': '30%', 'StaticShadows': 2048, 'Coronas': 20000
        },
        'High Performance': {
            'Peds': 150, 'Vehicles': 120, 'Buildings': 150000, 'Objects': 15000,
            'MemoryAvailable': '50%', 'StaticShadows': 4096, 'Coronas': 50000
        },
        'Modded': {
            'Peds': 255, 'Vehicles': 255, 'Buildings': 500000, 'Objects': 50000,
            'MemoryAvailable': 'unlimited', 'StaticShadows': 16384, 'Coronas': 200000
        },
        'Pushed to Farthest': {
            'Peds': 255, 'Vehicles': 255, 'Buildings': 1000000, 'Objects': 100000,
            'Dummys': 500000, 'ColModel': 100000, 'PedIntelligence': 255,
            'StreamingInfo': 50000, 'MemoryAvailable': 'unlimited', 'ExtraObjectsDir': 2048,
            'AtomicModels': 100000, 'DamageAtomicModels': 100000, 'TimeModels': 100000,
            'ClumpModels': 100000, 'VehicleModels': 100000, 'PedModels': 100000, 'WeaponModels': 100000,
            'PtrNodeSingle': 1000000, 'PtrNodeDouble': 1000000, 'PtrNode': 1000000,
            'EntryInfoNode': 50000, 'VisibleEntityPtrs': 500000, 'VisibleLodPtrs': 500000, 'AlphaEntityList': 50000,
            'StaticShadows': 16384, 'Coronas': 200000, 'ScriptSearchLights': 10000,
            'OutsideWorldWaterBlocks': 5000, 'StreamingObjectInstancesList': 200000,
            'TxdStore': 5000, 'AudioScriptObj': 1000, '2dEffects': 500,
            'EntitiesPerIpl': 10000, 'EntityIpl': 1000, 'PointRoute': 10000,
            'PatrolRoute': 10000, 'NodeRoute': 10000, 'Task': 100000, 'Event': 100000,
            'TaskAllocator': 100000, 'PedAttractors': 100000, 'VehicleStructs': 100000,
            'MatrixList': 100000, 'Treadables': 100, 'CollisionSize': 10000
        },
        # Hypothetical Rockstar 2007 final patch: what PS2->PC 2007 would ship
        # Stock was PS2 remnants (2004 port). 2007 patch = era-correct PC upscale for
        # Core2 Duo / 2GB RAM / 8800 GTS 640MB, like V Enhanced was for next-gen.
        # ~2-3x Stock, ~0.3x of Pushed max — stable, not meme. Quadrupled maxima stay for ridiculous manual.
        'Top of the 2007': {
            'Peds': 240, 'Vehicles': 230, 'Buildings': 260000, 'Objects': 42000,
            'Dummys': 120000, 'ColModel': 42000, 'PedIntelligence': 240,
            'StreamingInfo': 18000, 'MemoryAvailable': '512', 'ExtraObjectsDir': 1536, 'VRAM': 512,
            'AtomicModels': 28000, 'DamageAtomicModels': 28000, 'TimeModels': 28000,
            'ClumpModels': 28000, 'VehicleModels': 2200, 'PedModels': 2200, 'WeaponModels': 450,
            'PtrNodeSingle': 600000, 'PtrNodeDouble': 600000, 'PtrNode': 600000,
            'EntryInfoNode': 14000, 'VisibleEntityPtrs': 240000, 'VisibleLodPtrs': 240000, 'AlphaEntityList': 8000,
            'StaticShadows': 8192, 'Coronas': 80000, 'ScriptSearchLights': 4096,
            'OutsideWorldWaterBlocks': 1800, 'StreamingObjectInstancesList': 80000,
            'TxdStore': 3800, 'AudioScriptObj': 480, '2dEffects': 300,
            'EntitiesPerIpl': 3800, 'EntityIpl': 380, 'PointRoute': 3800,
            'PatrolRoute': 3800, 'NodeRoute': 3800, 'Task': 40000, 'Event': 40000,
            'TaskAllocator': 40000, 'PedAttractors': 14000, 'VehicleStructs': 14000,
            'MatrixList': 40000, 'Treadables': 48, 'CollisionSize': 8192
        },
        # --- Platform Emulation Presets (m0804 + m0813 cross-game liftable) ---
        # PS2 32MB + 4MB GS: 2004 original port limits. Enhanced SkyGfx dualPass PS2 pipes, 480i fonts. Pools as if PS2.
        'PS2 (32MB) — Exact': {
            'Peds': 110, 'Vehicles': 80, 'Buildings': 13000, 'Objects': 2500, 'Dummys': 10000, 'ColModel': 5000, 'PedIntelligence': 110,
            'StreamingInfo': 3500, 'MemoryAvailable': '32', 'ExtraObjectsDir': 128, 'VRAM': 32,
            'AtomicModels': 5000, 'DamageAtomicModels': 3000, 'TimeModels': 3000, 'ClumpModels': 5000, 'VehicleModels': 800, 'PedModels': 600, 'WeaponModels': 250,
            'PtrNodeSingle': 70000, 'PtrNodeDouble': 70000, 'PtrNode': 70000, 'EntryInfoNode': 2000, 'VisibleEntityPtrs': 20000, 'VisibleLodPtrs': 20000, 'AlphaEntityList': 500,
            'StaticShadows': 1024, 'Coronas': 5000, 'ScriptSearchLights': 512, 'OutsideWorldWaterBlocks': 200, 'StreamingObjectInstancesList': 8000,
            'TxdStore': 512, 'AudioScriptObj': 96, '2dEffects': 0, 'EntitiesPerIpl': 300, 'EntityIpl': 40, 'PointRoute': 300, 'PatrolRoute': 300, 'NodeRoute': 300, 'Task': 5000, 'Event': 5000,
            'TaskAllocator': 5000, 'PedAttractors': 2000, 'VehicleStructs': 2000, 'MatrixList': 5000, 'Treadables': 1, 'CollisionSize': 512,
            'SkyGfxMode': 'PS2'
        },
        # Xbox 64MB UMA NV2A: 480p Register Combiners, cubemap specular. ~2x PS2.
        'Xbox (64MB) — Exact': {
            'Peds': 140, 'Vehicles': 110, 'Buildings': 30000, 'Objects': 6000, 'Dummys': 25000, 'ColModel': 10000, 'PedIntelligence': 140,
            'StreamingInfo': 6000, 'MemoryAvailable': '64', 'ExtraObjectsDir': 256, 'VRAM': 64,
            'AtomicModels': 8000, 'DamageAtomicModels': 6000, 'TimeModels': 6000, 'ClumpModels': 8000, 'VehicleModels': 1200, 'PedModels': 1000, 'WeaponModels': 300,
            'PtrNodeSingle': 150000, 'PtrNodeDouble': 150000, 'PtrNode': 150000, 'EntryInfoNode': 4000, 'VisibleEntityPtrs': 50000, 'VisibleLodPtrs': 50000, 'AlphaEntityList': 1000,
            'StaticShadows': 2048, 'Coronas': 15000, 'ScriptSearchLights': 1024, 'OutsideWorldWaterBlocks': 400, 'StreamingObjectInstancesList': 16000,
            'TxdStore': 900, 'AudioScriptObj': 160, '2dEffects': 50, 'EntitiesPerIpl': 600, 'EntityIpl': 80, 'PointRoute': 600, 'PatrolRoute': 600, 'NodeRoute': 600, 'Task': 8000, 'Event': 8000,
            'TaskAllocator': 8000, 'PedAttractors': 4000, 'VehicleStructs': 4000, 'MatrixList': 8000, 'Treadables': 1, 'CollisionSize': 1024,
            'SkyGfxMode': 'Xbox'
        },
        # PS3 256+256 split, 720p enhanced. ~4x Xbox. With restored files later, font/display = PS3.
        'PS3 (512MB) — Enhanced': {
            'Peds': 180, 'Vehicles': 160, 'Buildings': 120000, 'Objects': 18000, 'Dummys': 60000, 'ColModel': 18000, 'PedIntelligence': 180,
            'StreamingInfo': 10000, 'MemoryAvailable': '256', 'ExtraObjectsDir': 512, 'VRAM': 256,
            'AtomicModels': 15000, 'DamageAtomicModels': 12000, 'TimeModels': 12000, 'ClumpModels': 15000, 'VehicleModels': 1600, 'PedModels': 1500, 'WeaponModels': 400,
            'PtrNodeSingle': 300000, 'PtrNodeDouble': 300000, 'PtrNode': 300000, 'EntryInfoNode': 7000, 'VisibleEntityPtrs': 120000, 'VisibleLodPtrs': 120000, 'AlphaEntityList': 3000,
            'StaticShadows': 4096, 'Coronas': 40000, 'ScriptSearchLights': 2048, 'OutsideWorldWaterBlocks': 800, 'StreamingObjectInstancesList': 40000,
            'TxdStore': 1800, 'AudioScriptObj': 300, '2dEffects': 150, 'EntitiesPerIpl': 1500, 'EntityIpl': 150, 'PointRoute': 1500, 'PatrolRoute': 1500, 'NodeRoute': 1500, 'Task': 15000, 'Event': 15000,
            'TaskAllocator': 15000, 'PedAttractors': 7000, 'VehicleStructs': 7000, 'MatrixList': 15000, 'Treadables': 10, 'CollisionSize': 2048,
            'SkyGfxMode': 'PS3'
        },
        # PS4 8GB GDDR5 unified, 1080p Modern. SkyGfx full pipes, no dualPass.
        'PS4 (8GB) — Modern': {
            'Peds': 255, 'Vehicles': 230, 'Buildings': 500000, 'Objects': 50000, 'Dummys': 250000, 'ColModel': 60000, 'PedIntelligence': 255,
            'StreamingInfo': 30000, 'MemoryAvailable': '1024', 'ExtraObjectsDir': 1024, 'VRAM': 2048,
            'AtomicModels': 50000, 'DamageAtomicModels': 40000, 'TimeModels': 40000, 'ClumpModels': 50000, 'VehicleModels': 2500, 'PedModels': 2500, 'WeaponModels': 600,
            'PtrNodeSingle': 600000, 'PtrNodeDouble': 600000, 'PtrNode': 600000, 'EntryInfoNode': 20000, 'VisibleEntityPtrs': 300000, 'VisibleLodPtrs': 300000, 'AlphaEntityList': 15000,
            'StaticShadows': 8192, 'Coronas': 100000, 'ScriptSearchLights': 4096, 'OutsideWorldWaterBlocks': 2000, 'StreamingObjectInstancesList': 100000,
            'TxdStore': 3000, 'AudioScriptObj': 500, '2dEffects': 300, 'EntitiesPerIpl': 3000, 'EntityIpl': 300, 'PointRoute': 3000, 'PatrolRoute': 3000, 'NodeRoute': 3000, 'Task': 40000, 'Event': 40000,
            'TaskAllocator': 40000, 'PedAttractors': 12000, 'VehicleStructs': 12000, 'MatrixList': 40000, 'Treadables': 60, 'CollisionSize': 4096,
            'SkyGfxMode': 'PS4'
        },
        # PS5 16GB GDDR6 SSD 4K Next-Gen. Pushed-class pools, SkyGfx 4K pipes. Lite option = host-accommodated via auto VRAM.
        'PS5 (16GB) — Next-Gen': {
            'Peds': 255, 'Vehicles': 255, 'Buildings': 1000000, 'Objects': 100000, 'Dummys': 500000, 'ColModel': 100000, 'PedIntelligence': 255,
            'StreamingInfo': 50000, 'MemoryAvailable': '2048', 'ExtraObjectsDir': 2048, 'VRAM': 4096,
            'AtomicModels': 100000, 'DamageAtomicModels': 80000, 'TimeModels': 80000, 'ClumpModels': 100000, 'VehicleModels': 4000, 'PedModels': 4000, 'WeaponModels': 800,
            'PtrNodeSingle': 1000000, 'PtrNodeDouble': 1000000, 'PtrNode': 1000000, 'EntryInfoNode': 40000, 'VisibleEntityPtrs': 500000, 'VisibleLodPtrs': 500000, 'AlphaEntityList': 30000,
            'StaticShadows': 16384, 'Coronas': 200000, 'ScriptSearchLights': 8192, 'OutsideWorldWaterBlocks': 5000, 'StreamingObjectInstancesList': 200000,
            'TxdStore': 5000, 'AudioScriptObj': 900, '2dEffects': 500, 'EntitiesPerIpl': 8000, 'EntityIpl': 800, 'PointRoute': 8000, 'PatrolRoute': 8000, 'NodeRoute': 8000, 'Task': 80000, 'Event': 80000,
            'TaskAllocator': 80000, 'PedAttractors': 30000, 'VehicleStructs': 30000, 'MatrixList': 80000, 'Treadables': 100, 'CollisionSize': 8192,
            'SkyGfxMode': 'PS5'
        }
    }
    
    def __init__(self, parent, game_path: Path, db_manager):
        self.parent = parent
        self.game_path = game_path
        self.db_manager = db_manager
        self.current_values = {}
        self.category_frames = {}
        self.scroll_canvas = None
        self.scroll_region = None
        
    def create_scroll_window(self):
        """Create a Vista-style scroll window with categories"""
        # Main container
        container = tk.Frame(self.parent, bg=self.COLORS['bg_gradient_top'])
        
        # Title
        title = tk.Label(container, text="🔧 Limit Adjuster Settings", 
                        font=('Segoe UI', 14, 'bold'), 
                        bg=self.COLORS['bg_gradient_top'],
                        fg=self.COLORS['text_primary'])
        title.pack(pady=(10, 5), padx=10, anchor='w')
        
        # Search bar
        search_frame = tk.Frame(container, bg=self.COLORS['bg_gradient_bottom'])
        search_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT)
        search_entry.bind('<KeyRelease>', self._on_search)
        
        ttk.Button(search_frame, text="🔍 Search", command=self._on_search).pack(side=tk.LEFT, padx=(5, 0))
        
        # Scrollable canvas
        canvas_frame = tk.Frame(container)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Create scrollable area
        self.scroll_region = tk.Canvas(canvas_frame, bg=self.COLORS['bg_gradient_bottom'],
                                       highlightthickness=0, height=400)
        
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.scroll_region.yview)
        self.scroll_region.configure(yscrollcommand=scrollbar.set)
        
        self.scroll_region.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Inner frame for content
        self.scroll_canvas = tk.Frame(self.scroll_region, bg=self.COLORS['frame_bg'])
        self.scroll_region.create_window((0, 0), window=self.scroll_canvas, anchor='nw')
        
        self.scroll_canvas.bind('<Configure>', self._on_canvas_configure)
        self.scroll_region.bind('<Configure>', self._on_scroll_configure)
        
        # Create category tabs
        self._create_category_tabs(container)
        
        # Create preset buttons
        self._create_preset_buttons(container)
        
        # Create category content
        self._create_category_content()
        
        # Apply button
        apply_btn = ttk.Button(container, text="✅ Apply All Changes", 
                              command=self._apply_all_changes,
                              style='Accent.TButton')
        apply_btn.pack(pady=10)
        
        return container
    
    def _on_canvas_configure(self, event):
        """Update scroll region when canvas size changes"""
        self.scroll_region.configure(scrollregion=self.scroll_region.bbox('all'))
    
    def _on_scroll_configure(self, event):
        """Configure scroll region"""
        self.scroll_region.configure(scrollregion=self.scroll_region.bbox('all'))
    
    def _create_category_tabs(self, parent):
        """Create category tabs at the top"""
        tab_frame = tk.Frame(parent, bg=self.COLORS['bg_gradient_top'])
        tab_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        self.tab_vars = {}
        for category in self.LIMIT_CATEGORIES.keys():
            var = tk.BooleanVar()
            self.tab_vars[category] = var
            
            btn = tk.Checkbutton(tab_frame, text=f" {category} ", 
                                variable=var,
                                command=lambda c=category: self._toggle_category(c),
                                bg=self.COLORS['frame_bg'],
                                activebackground=self.COLORS['button_hover'],
                                selectcolor=self.COLORS['category_header'])
            btn.pack(side=tk.LEFT, padx=2)
    
    def _toggle_category(self, category):
        """Toggle category visibility"""
        if category in self.category_frames:
            frame = self.category_frames[category]
            if frame.winfo_viewable():
                frame.pack_forget()
            else:
                frame.pack(fill=tk.X, padx=10, pady=2)
    
    def _create_preset_buttons(self, parent):
        """Create preset selection buttons"""
        preset_frame = tk.Frame(parent, bg=self.COLORS['bg_gradient_top'])
        preset_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        ttk.Label(preset_frame, text="Presets:", font=('Segoe UI', 9, 'bold')).pack(anchor=tk.W)
        
        for preset_name in self.PRESETS.keys():
            btn = tk.Button(preset_frame, text=preset_name,
                           command=lambda p=preset_name: self._apply_preset(p),
                           bg=self.COLORS['preset_button'],
                           fg='white',
                           relief=tk.FLAT,
                           font=('Segoe UI', 8))
            btn.pack(side=tk.LEFT, padx=2)
            btn.bind('<Enter>', lambda e, b=btn: b.config(bg=self.COLORS['preset_button_hover']))
            btn.bind('<Leave>', lambda e, b=btn: b.config(bg=self.COLORS['preset_button']))
    
    def _create_category_content(self):
        """Create content for each category with responsive grid layout"""
        for category, data in self.LIMIT_CATEGORIES.items():
            frame = tk.Frame(self.scroll_canvas, bg=self.COLORS['frame_bg'],
                            relief=tk.SUNKEN, borderwidth=2)
            frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=2)
            
            # Category header with icon
            header = tk.Label(frame, text=f"{data['icon']} {category}", 
                             font=('Segoe UI', 11, 'bold'),
                             bg=self.COLORS['category_header'],
                             fg=self.COLORS['text_primary'])
            header.pack(fill=tk.X, padx=10, pady=5)
            
            # Settings grid - responsive layout
            grid_frame = tk.Frame(frame, bg=self.COLORS['frame_bg'])
            grid_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            # Configure grid weights for responsiveness
            for i in range(6):  # Up to 6 columns
                grid_frame.grid_columnconfigure(i, weight=1)
            
            for i, setting in enumerate(data['settings']):
                # Calculate column based on available space
                col = i % 6
                row = i // 6
                
                # Setting cell
                cell = tk.Frame(grid_frame, bg=self.COLORS['frame_bg'], padx=5, pady=3)
                cell.grid(row=row, column=col, sticky='ew', padx=2, pady=1)
                
                # Setting name
                name_label = tk.Label(cell, text=setting['name'], 
                                     font=('Segoe UI', 9),
                                     bg=self.COLORS['frame_bg'],
                                     anchor='w')
                name_label.pack(anchor='w')
                
                # Setting value - load saved from DB if present
                saved = None
                try:
                    if self.db_manager:
                        v = self.db_manager.get_limit('gtasa', setting['name'])
                        if v is not None:
                            saved = v
                except Exception:
                    saved = None
                if setting['type'] == 'int':
                    init_val = int(saved) if saved is not None else setting['default']
                    var = tk.IntVar(value=init_val)
                    entry = ttk.Entry(cell, textvariable=var, width=6)
                    entry.pack(anchor='w')
                    self.current_values[setting['name']] = var
                elif setting['type'] == 'str' and 'options' in setting:
                    init_val = str(saved) if saved is not None else setting['default']
                    var = tk.StringVar(value=init_val)
                    combo = ttk.Combobox(cell, textvariable=var, values=setting['options'], 
                                          width=8, state='readonly')
                    combo.pack(anchor='w')
                    self.current_values[setting['name']] = var
                else:
                    init_val = str(saved) if saved is not None else setting['default']
                    var = tk.StringVar(value=init_val)
                    entry = ttk.Entry(cell, textvariable=var, width=10)
                    entry.pack(anchor='w')
                    self.current_values[setting['name']] = var
                
                # Description (smaller font)
                desc_label = tk.Label(cell, text=setting['description'], 
                                     font=('Segoe UI', 7),
                                     bg=self.COLORS['frame_bg'],
                                     fg=self.COLORS['text_disabled'],
                                     wraplength=150,
                                     justify='left')
                desc_label.pack(anchor='w', pady=(2, 0))
            
            self.category_frames[category] = frame
    
    def _on_search(self, event=None):
        """Handle search functionality"""
        query = self.search_var.get().lower()
        if not query:
            return
        
        # Highlight matching settings
        for category, frame in self.category_frames.items():
            for widget in frame.winfo_children():
                if isinstance(widget, tk.Label):
                    text = widget.cget('text').lower()
                    if query in text:
                        widget.config(bg=self.COLORS['button_hover'])
                    else:
                        widget.config(bg=self.COLORS['frame_bg'])
    
    # SkyGfx mode mapping for platform presets — emulates period pipes/fonts/displays
    SKYGFX_MODES = {
        'PS2':  {'buildingPipe':'PS2', 'vehiclePipe':'PS2', 'pipeline':'PS2', 'colorFilter':'PS2', 'dualPassBuilding':'1', 'dualPassVehicle':'1', 'dualPassPed':'1', 'ps2ModulateBuilding':'1', 'usePCTimecyc':'0'},
        'Xbox': {'buildingPipe':'Xbox', 'vehiclePipe':'Xbox', 'pipeline':'Xbox', 'colorFilter':'Xbox', 'dualPassBuilding':'0', 'dualPassVehicle':'0', 'envSpecularityMult':'1.2'},
        'PS3':  {'buildingPipe':'PBR', 'vehiclePipe':'PBR', 'pipeline':'PBR', 'colorFilter':'Modern', 'dualPassBuilding':'0', 'detailMaps':'1'},
        'PS4':  {'buildingPipe':'PBR', 'vehiclePipe':'Modern', 'pipeline':'PBR', 'colorFilter':'Modern', 'detailMaps':'1', 'ssaoEnable':'1'},
        'PS5':  {'buildingPipe':'PBR', 'vehiclePipe':'Modern', 'pipeline':'PBR', 'colorFilter':'Modern', 'detailMaps':'1', 'ssaoEnable':'1', 'envMapSize':'256'},
    }

    def _apply_skygfx_mode(self, mode: str):
        """Write SkyGfx ini for period emulation — optional, non-fatal"""
        try:
            overrides = self.SKYGFX_MODES.get(mode)
            if not overrides:
                return
            ini = self.game_path / 'skygfx.ini'
            # read existing
            lines = []
            if ini.exists():
                with open(ini, 'r') as f:
                    lines = f.read().splitlines()
            # parse into dict preserving order
            out = []
            section = None
            seen = set()
            sky_section = False
            for ln in lines:
                s = ln.strip()
                if s.startswith('[') and s.endswith(']'):
                    section = s[1:-1]
                    sky_section = (section == 'SkyGfx')
                    out.append(ln)
                elif sky_section and '=' in ln and not s.startswith(';'):
                    k = ln.split('=',1)[0].strip()
                    if k in overrides:
                        out.append(f"{k} = {overrides[k]}")
                        seen.add(k)
                    else:
                        out.append(ln)
                else:
                    out.append(ln)
            # append missing keys inside SkyGfx section or create it
            if not any(l.strip()=='[SkyGfx]' for l in out):
                out.append('[SkyGfx]')
            # insert missing overrides after [SkyGfx] header
            if len([k for k in overrides if k not in seen])>0:
                # find insert pos
                try:
                    idx = next(i for i,l in enumerate(out) if l.strip()=='[SkyGfx]')
                    for k,v in overrides.items():
                        if k not in seen:
                            out.insert(idx+1, f"{k} = {v}")
                            idx+=1
                except Exception:
                    for k,v in overrides.items():
                        if k not in seen:
                            out.append(f"{k} = {v}")
            with open(ini, 'w') as f:
                f.write("\n".join(out) + "\n")
            try:
                self.db_manager.set_limit('gtasa', 'SkyGfxMode', mode)
            except Exception:
                pass
        except Exception:
            pass

    def _apply_preset(self, preset_name: str):
        """Apply a preset — Top of the 2007 only auto-scales VRAM/MemoryAvailable (1/4 RAM), mesh stays at realistic 2007 values"""
        preset = dict(self.PRESETS[preset_name])
        if preset_name == 'Top of the 2007':
            try:
                from utils.system_utils import SystemUtils
                cfg = SystemUtils.get_top2007_auto_config()
                preset['VRAM'] = cfg['VRAM']
                preset['MemoryAvailable'] = cfg['MemoryAvailable']
            except Exception:
                pass
        # SkyGfx period emulation if preset has it
        if 'SkyGfxMode' in preset:
            self._apply_skygfx_mode(preset['SkyGfxMode'])
        for key, value in preset.items():
            if key == 'SkyGfxMode':
                continue
            if key in self.current_values:
                try:
                    self.current_values[key].set(value)
                except Exception:
                    pass
    
    def _apply_all_changes(self):
        """Apply all changes to the database and INI file"""
        changes = {}
        for name, var in self.current_values.items():
            changes[name] = var.get()
        
        # Save to database
        for name, value in changes.items():
            self.db_manager.set_limit('gtasa', name, value)
        
        # Write to INI file
        self._write_ini_file(changes)
        
        messagebox.showinfo("Success", f"Applied {len(changes)} settings to game configuration")
    
    def _write_ini_file(self, changes: Dict[str, Any]):
        """Write changes to the INI file"""
        ini_path = self.game_path / 'III.VC.SA.LimitAdjuster.ini'
        
        # Read existing INI
        config = {}
        current_section = None
        
        if ini_path.exists():
            with open(ini_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('[') and line.endswith(']'):
                        current_section = line[1:-1]
                        config[current_section] = {}
                    elif '=' in line and current_section:
                        key, value = line.split('=', 1)
                        config[current_section][key.strip()] = value.strip()
        
        # Update with new values
        for name, value in changes.items():
            # Find which section this setting belongs to
            for section in ['SALIMITS', 'VCLIMITS', 'GTA3LIMITS', 'OPTIONS']:
                if section in config and name in config[section]:
                    config[section][name] = str(value)
                    break
        
        # Write back
        with open(ini_path, 'w') as f:
            for section, settings in config.items():
                f.write(f'[{section}]\n')
                for key, value in settings.items():
                    f.write(f'{key} = {value}\n')
                f.write('\n')