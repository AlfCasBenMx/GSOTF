"""Explicit cleanup of the legacy temporary saved-image folder."""
import argparse
from runtime import BASE_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    folder = BASE_DIR / "TempSavedImages"
    if folder.is_symlink():
        raise ValueError("Refusing a symlinked folder")
    files = [p for p in folder.glob("*.jpg") if p.is_file() and not p.is_symlink()]
    if args.apply:
        for path in files:
            path.unlink()
    print("Selected:", len(files), "apply:", args.apply)


if __name__ == "__main__":
    main()
