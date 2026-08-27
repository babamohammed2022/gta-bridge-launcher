"""GTA SAS 1987 Installer — first-class project subsystem.

Usage:
    import installer_src as sas87
    sas87.Config.ensure_cache_dirs()
    sas87.Downloader.download(...)
    sas87.Hashes.detect(...)
"""

from __future__ import annotations

__version__ = "3.0.0"
__all__ = [
    "Downloader", "Extractor", "Detector", "Hashes",
    "Scraper", "Stages", "Cache", "Backup", "NoCD", "Config",
]

# --- Import all public modules ---
from . import config as Config
from . import cache as Cache
from . import backup as Backup
from . import downloader as Downloader
from . import extractor as Extractor
from . import sa_detector as Detector
from . import sa_hashes as Hashes
from . import scraper as Scraper
from . import installer_stages as Stages
from . import gamecopyworld as NoCD