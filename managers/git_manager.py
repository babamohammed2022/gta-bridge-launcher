"""
Git Manager - Handles cloning and updating of limit extender repositories
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Optional

try:
    import git
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False


class GitManager:
    """Manages cloning and updating of limit extender repositories"""
    
    REPOS = {
        'gta3': 'https://github.com/ThirteenAG/III.VC.SA.LimitAdjuster',
        'gtavc': 'https://github.com/ThirteenAG/III.VC.SA.LimitAdjuster',
        'gtasa': 'https://github.com/ThirteenAG/III.VC.SA.LimitAdjuster',
        'fastman92': 'https://github.com/fastman92/limit-adjuster-for-gta-sa'
    }
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.repos_path = self.base_path / 'repos'
        try:
            self.repos_path.mkdir(parents=True, exist_ok=True)
        except OSError:
            # read-only or invalid location (e.g. friend install without dev
            # layout) — repo management is optional, degrade gracefully
            self.repos_path = None
    
    def clone_all_repos(self) -> Dict[str, str]:
        """Clone all limit extender repositories"""
        if not GIT_AVAILABLE:
            return {'error': 'GitPython not installed. Run: pip install gitpython'}
        
        results = {}
        if self.repos_path is None:
            return {'error': 'repos dir unavailable (read-only install)'}
        for game, url in self.REPOS.items():
            try:
                repo_path = self.repos_path / game
                if not repo_path.exists():
                    git.Repo.clone_from(url, str(repo_path))
                    results[game] = 'cloned'
                else:
                    results[game] = 'already_exists'
            except Exception as e:
                results[game] = f'error: {str(e)}'
        return results

    def update_repos(self) -> Dict[str, str]:
        """Update all cloned repositories"""
        if not GIT_AVAILABLE:
            return {'error': 'GitPython not installed'}
        if self.repos_path is None:
            return {'error': 'repos dir unavailable (read-only install)'}

        results = {}
        for game in self.REPOS.keys():
            repo_path = self.repos_path / game
            if repo_path.exists():
                try:
                    repo = git.Repo(str(repo_path))
                    repo.remotes.origin.pull()
                    results[game] = 'updated'
                except Exception as e:
                    results[game] = f'error: {str(e)}'
            else:
                results[game] = 'not_found'
        return results
    
    def get_repo_path(self, game: str) -> Optional[Path]:
        """Get the path to a specific repository"""
        repo_path = self.repos_path / game
        return repo_path if repo_path.exists() else None
    
    def is_repo_cloned(self, game: str) -> bool:
        """Check if a repository is already cloned"""
        return (self.repos_path / game).exists()