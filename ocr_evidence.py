"""Small local evidence files; no image decoding or extra network calls."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


def preserve(data, full_image, saved_folder):
    folder = Path(saved_folder).parent / "OCREvidence"
    folder.mkdir(parents=True, exist_ok=True)
    event = Path(full_image).stem + "_" + uuid4().hex[:12]
    crop = folder / (event + ".jpg")
    with crop.open("xb") as stream:
        stream.write(data)
    record = {"event": event, "full_image": Path(full_image).name,
              "crop": crop.name, "submitted_at_utc": datetime.now(timezone.utc).isoformat(),
              "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return folder / (event + ".json"), record


def finish(path, record, status, lines, plates):
    record.update(ocr_status=status, raw_lines=lines, normalized_candidates=plates,
                  genyus_eligible_candidates=[p for p in plates if 4 < len(p) < 8])
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(temporary), str(path))
