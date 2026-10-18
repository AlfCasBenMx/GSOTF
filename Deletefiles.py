"""Retention for BOTH archive folders. Dry-run unless --apply is explicit."""
import argparse
from pathlib import Path
import shutil
import time
from runtime import BASE_DIR
import HandlingEvents as events


def cleanup(base=BASE_DIR, days=20, min_free_bytes=2*1024**3, apply=False, now=None):
    base = Path(base).resolve()
    if days < 1 or min_free_bytes < 0:
        raise ValueError("Retention must be >=1 day and free-space floor >=0")
    now = time.time() if now is None else now
    candidates = []
    for name in ("SavedPlates", "ErrorOCR"):
        folder = base / name
        if folder.is_symlink():
            raise ValueError("Archive folder must not be a symlink")
        for path in folder.glob("*.jpg"):
            if not path.is_symlink() and path.is_file():
                stat = path.stat()
                candidates.append((stat.st_mtime, path, stat.st_size))
    free = shutil.disk_usage(base).free
    removed = []
    for modified, path, size in sorted(candidates):
        # Never touch just-captured evidence; keep both folders' policy identical.
        if now - modified < 120:
            continue
        if modified >= now - days*86400 and free >= min_free_bytes:
            continue
        if apply:
            path.unlink()
            free = shutil.disk_usage(base).free
        else:
            free += size
        removed.append(str(path))
    events.logEvent("Image retention apply=%s selected=%d" % (apply, len(removed)))
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--days", type=int, default=20)
    parser.add_argument("--min-free-gb", type=float, default=2)
    args = parser.parse_args()
    print("Selected images:", len(cleanup(days=args.days,
          min_free_bytes=int(args.min_free_gb*1024**3), apply=args.apply)))


if __name__ == "__main__":
    main()
