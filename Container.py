"""Upload a snapshot only when explicitly called; no import-time uploads."""
from pathlib import Path
import os
import requests
import StartSettings
from runtime import BASE_DIR


def main():
    StartSettings.startVar(required=("accountName", "accountKey", "serialLiper"))
    endpoint = os.environ.get("GDF_IMAGE_INFO_URL")
    if not endpoint:
        raise ValueError("GDF_IMAGE_INFO_URL is not configured")
    from azure.storage.blob import BlobServiceClient
    files = list((BASE_DIR / "TempImages").glob("*.jpg"))
    if not files:
        raise RuntimeError("No temporary image available")
    image = max(files, key=lambda p: p.stat().st_mtime)
    # Read fully before upload so later temporary cleanup cannot remove an open input.
    data = image.read_bytes()
    with BlobServiceClient(account_url="https://%s.blob.core.windows.net" % StartSettings.accountName,
            credential=StartSettings.accountKey, connection_timeout=5, read_timeout=15,
            retry_total=0) as client:
        blob = client.get_blob_client(StartSettings.containerName or "liperimages", StartSettings.serialLiper + ".jpg")
        blob.upload_blob(data, overwrite=True)
        with requests.post(endpoint, json={"serialLiper": StartSettings.serialLiper,
                "imageUrl": blob.url, "captureDate": image.stem}, timeout=(5, 15)) as response:
            response.raise_for_status()


if __name__ == "__main__":
    main()
