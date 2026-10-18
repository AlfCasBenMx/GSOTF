"""Copy matching archive photos to an explicitly supplied destination."""
import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    for source in args.source.glob("*.jpg"):
        if source.is_file() and source.name.startswith(args.prefix):
            target = args.destination / source.name
            if not target.exists():
                shutil.copy2(source, target)


if __name__ == "__main__":
    main()
