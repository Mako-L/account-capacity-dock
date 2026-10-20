"""Shared cache location for the native dock and collectors."""
import os
from pathlib import Path
import sys


def cache_dir(home=None, platform=None):
    home = Path.home() if home is None else Path(home)
    platform = sys.platform if platform is None else platform
    if platform == 'darwin':
        return home / 'Library/Application Support/Mako Capacity'
    if platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', home / 'AppData/Local')) / 'mako-capacity'
    return Path(os.environ.get('XDG_CACHE_HOME', home / '.cache')) / 'mako-capacity'
