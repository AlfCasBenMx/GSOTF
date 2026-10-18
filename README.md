# GSOTF / GDF

Raspberry Pi plate reader. Work branch: `fixes/runtime-reliability`.

## Preserved behavior

- OCR processes only the **last** detection with confidence >=45% per image.
- Selected full captures stay in SavedPlates; unsuccessful OCR also keeps a copy
  in ErrorOCR. This duplication is intentional.
- Camera configuration remains 3200x2592 with continuous autofocus.
- Plate normalization and the Genyus payload keep the existing contract.

## Reliability changes

- One active OCR job, no growing queue. Frames arriving while busy are not sent
  to OCR. The stationary counter advances only on accepted jobs and resets on
  movement or five seconds without detections.
- In-flight temporary images are protected against the reader's cleanup.
- API calls have timeouts. POSTs are retried only after explicit HTTP 429;
  timeouts and 5xx may indicate an already-processed request and are not retried.
  A rejected authentication can trigger one new token and retry. No offline
  delivery queue is implemented; failed submissions require operational review.
- Azure OCR polling is bounded; the installed msrest client has a 15-second
  socket timeout and automatic retries disabled. The 30-second polling deadline
  can be exceeded by one in-progress network operation.
- Rotating logs in Logs/runtime.log include failures and tracebacks with known
  configured secrets redacted. Shutdown waits for the OCR worker and closes the
  camera. Hardware errors return a nonzero process exit code.
- Reboot requests use full UTC SQLite timestamps and a transaction to enforce
  at most three in 30 minutes. Reboot is disabled by default; service restart is
  preferred. No database schema is modified automatically.
- Heartbeat is a separate process. Network speed is measured eth0/wlan0 traffic
  throughput in Mbps, **not** available internet bandwidth. Unsupported sensor
  values use an "unknown" marker; confirm the receiving contract when adding integrations.

## Configuration

Keep the existing Config.xml on the device. Never commit it. Config.example.xml
documents the expected field names. GDF_CONFIG overrides its location; GDF_SERIAL
can override the device serial for tests. Credentials can also be supplied as
GDF_OCR_KEY, GDF_GENYUS_KEY, GDF_STORAGE_KEY and the other variables in StartSettings.
Missing required settings abort startup. Optional SMTP, Telegram and Azure
Function settings are documented in deploy/runtime.example.env. Existing SMTP
and Telegram credentials must be migrated from the private originals before
those integrations can run. They are not copied into source.

## Dependencies

The initial requirements.txt records observed versions, not a reproducible lock.
Raspberry Pi OS Python 3.9, libcamera, Picamera2, model files and label_map.pbtxt
remain required. Preserve the working environment; do not upgrade it blindly.
Container.py optionally needs the modern azure-storage-blob SDK (BlobServiceClient),
which is incompatible with the observed legacy azure-storage 0.36 API.
The installer validates and reuses compatible environments before creating a new one. See the Spanish installation guide for the tested scope.

## Tests

Run on Python 3.9 with psutil and the existing Azure OCR/msrest SDK installed:

```sh
python3 -m unittest discover -s tests -v
```

Tests simulate API responses and use temporary files/SQLite. They do not contact
Azure/Genyus, send notifications, reboot or open the camera. GitHub Actions runs
these same checks. Camera/model execution, real Azure OCR and both heartbeat destinations were also checked on Caucel4. A clean-device dependency installation is still unqualified; the historical OCR test had a Y/V recognition discrepancy.

## Image retention

Preview selection without deleting:

```sh
python3 Deletefiles.py
```

Explicit cleanup: `python3 Deletefiles.py --apply --days 20 --min-free-gb 2`.
Applies equally to SavedPlates and ErrorOCR. It deletes JPGs older than 20 days,
then oldest JPGs as needed for 2 GiB free space, even within 20 days. Images newer
than two minutes and symlinks are skipped. This is a retention ceiling, not a
guarantee to preserve 20 days. Other files and directories are not removed.
The supplied hourly systemd timer is **not enabled automatically**.

## Deployment reference and rollback

Caucel4 now runs the prepared copy at `/opt/gdf-test-reuse-20261018`, reusing
`/usr/bin/python3` and pi's compatible libraries. The previous code remains at
`/home/pi/Desktop/GDF`; the switch backup is under
`/home/pi/backups/switch-installed-20261018`. Archived photos and OCR evidence
are shared through links to their existing directories. Cleanup stays disabled.
See `docs/INSTALACION.md` for verification and the exact rollback procedure.
These are reference deployment paths, not live status.

Legacy standalone tools now have main guards and no import-time side effects.
SendNotifiactions.py is a compatibility shim. The identical, misspelled
SendNotifiactions.py.py duplicate is retired. Stop_main.py targets the systemd
service, not a Python process guessed by name. MaxbotixTTL returns millimetres;
its exact sensor frame format must be verified against the installed model.

Automatic deployment from GitHub is not enabled. The workflow validates tests only; it has no Raspberry credentials or deployment step.

## Second heartbeat destination

GDF_HEALTH_URL sets an HTTPS receiver, GDF_HEALTH_TOKEN its bearer write token,
and GDF_HEALTH_LABEL the public device label. Store these only in the device's
private runtime.env. Both destinations run independently with the same metric
sample; a failure in either is logged without preventing the other attempt.
The Genyus payload is unchanged. The second destination receives UTC send time,
health metrics and the age of the last processed frame. It receives no photos,
plate text, Genyus credentials, IP addresses or network configuration.
The receiver assigns its own receipt timestamp. Public status excludes the raw
device serial. The dashboard refreshes every 10 seconds and marks devices offline
after 90 seconds without a new heartbeat; a fresh heartbeat alone does not prove
that plate delivery to Genyus works.


OCR evidence: OCREvidence/ stores the exact JPEG bytes submitted to OCR plus a JSON sidecar with UTC submission time, source capture name, SHA256, raw OCR lines and normalized candidates. Candidates do not confirm Genyus delivery. No extra OCR requests or image processing. Evidence write failures are logged and do not block OCR. Files stay local and are ignored by Git; automatic cleanup remains disabled.

## Fresh Raspberry Pi installations

Documentación en español: [funcionamiento y flujo de la aplicación](docs/FUNCIONAMIENTO.md)
y [instalación, configuración y diagnóstico](docs/INSTALACION.md).

See [the Spanish installer guide](deploy/INSTALL_PI_ES.md). The installer targets
Pi 4 / Bullseye ARM64 / Python 3.9 and produces private structured error reports.
It refuses existing installations, keeps cleanup off, and requires local secret
configuration plus hardware checks before starting. Clean-device qualification
is still required; installer unit tests do not substitute for that deployment.


## Packaged artifacts

- [Raspberry Pi installer with model](releases/GDF_instalador_pi4.tar.gz)
- [Installer SHA256](releases/GDF_instalador_pi4.tar.gz.sha256)
- [Offline documentation and diagrams](releases/LIPER_documentacion.zip)
- [Application manual](docs/LIPER_funcionamiento.html)
- [Installation manual](docs/LIPER_instalacion.html)

The allowlisted installer archive contains the model and example configuration,
not live keys, photos or runtime logs. Extract the documentation ZIP locally to
view the HTML manuals and diagrams. Real credentials stay in ignored files.
