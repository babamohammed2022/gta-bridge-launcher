"""Archive probing + readme detection for package installs.

Algorithm inspired by Wrye Bash archives/reReadMe handling (GPL);
clean-room implementation. Extraction itself lives in
installer_src.extractor; this module only inspects.
"""
import os
import re
import zipfile

_README_RE = re.compile(
    r'(^|/)(readme|read me|lisez.?moi|docs?|licen[cs]e|changelog|version)'
    r'([._-].*)?\.(txt|md|pdf|html?)$', re.IGNORECASE)
_OK_CHARS = re.compile(r'[^A-Za-z0-9 _\-\.()]')


def _extractor():
    try:
        from installer_src import extractor
        return extractor
    except ImportError:
        return None


def list_archive(path):
    """Return [rel paths] inside archive. .zip native; .7z/.rar delegated."""
    low = path.lower()
    if low.endswith('.zip'):
        with zipfile.ZipFile(path) as z:
            return [i.filename for i in z.infolist() if not i.is_dir()]
    ex = _extractor()
    if ex is None:
        raise RuntimeError('archive type unsupported (installer_src missing): %s'
                           % path)
    if hasattr(ex, 'list_archive'):
        return ex.list_archive(path)
    raise RuntimeError('7z/rar listing unavailable (py7zr/rarfile missing?): %s'
                       % path)


def find_readme(namelist):
    """Shallowest readme-ish path, tie-broken by shortest name."""
    hits = [n for n in namelist if _README_RE.search(n.replace(os.sep, '/'))]
    if not hits:
        return None
    return sorted(hits, key=lambda n: (n.count('/'), len(n)))[0]


def _first_line(path, limit=512):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f.read(limit).splitlines():
                s = line.strip().strip('#*= ').strip()
                if s:
                    return s[:48]
    except OSError:
        pass
    return ''


def suggest_pack_name(archive_path, namelist=(), readme_text=''):
    """Derive install folder name: readme title line else archive stem."""
    if readme_text:
        for line in readme_text.splitlines():
            s = line.strip().strip('#*= ').strip()
            if s:
                return _OK_CHARS.sub('', s)[:48].strip() or _stem(archive_path)
    return _stem(archive_path)


def _stem(archive_path):
    base = os.path.basename(archive_path)
    for ext in ('.tar.gz', '.zip', '.7z', '.rar', '.001', '.tar'):
        if base.lower().endswith(ext):
            base = base[:-len(ext)]
            break
    return _OK_CHARS.sub('', base).strip() or 'unnamed_pack'


def top_level_dirs(namelist):
    """BAIN-style single-folder detection: dirs at archive root."""
    tops = set()
    for n in namelist:
        n = n.replace(os.sep, '/').lstrip('/')
        if '/' in n:
            tops.add(n.split('/')[0])
    return sorted(tops)
