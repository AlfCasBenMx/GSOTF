"""Optional ORB comparison utility, with no import-time file operations."""
import argparse
from pathlib import Path


def orb_sim(first, second, thresh=51):
    import cv2
    images = [cv2.imread(str(p), 0) for p in (first, second)]
    if any(image is None for image in images):
        raise ValueError("Image could not be decoded")
    orb = cv2.ORB_create()
    descriptors = [orb.detectAndCompute(image, None)[1] for image in images]
    if any(d is None for d in descriptors):
        return 0.0
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(*descriptors)
    return sum(m.distance < thresh for m in matches)/len(matches) if matches else 0.0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    args = parser.parse_args()
    print(orb_sim(args.first, args.second))
