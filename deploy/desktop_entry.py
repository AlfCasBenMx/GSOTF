"""Desktop launcher: run an extracted package, or unpack the repository's release."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def package_root(base):
    base = Path(base)
    if (base / 'release-manifest.json').is_file():
        return base
    archive = base / 'releases/GDF_instalador_pi4.tar.gz'
    checksum = archive.with_suffix(archive.suffix + '.sha256')
    expected = checksum.read_text(encoding='ascii').split()[0]
    if len(expected) != 64 or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise ValueError('El paquete no coincide con su SHA256. Descargalo de nuevo.')
    destination = Path(tempfile.mkdtemp(prefix='liper-installer-'))
    with tarfile.open(str(archive)) as source:
        for item in source.getmembers():
            path = (destination / item.name).resolve()
            if destination.resolve() not in path.parents or not (item.isfile() or item.isdir()):
                raise ValueError('Contenido de paquete no permitido')
        source.extractall(str(destination))
    root = destination / 'gdf-installer'
    if not (root / 'release-manifest.json').is_file():
        raise ValueError('El paquete no contiene su manifiesto')
    return root


def main():
    try:
        base = package_root(Path(__file__).resolve().parents[1])
        command = ['bash', str(base / 'deploy/install_desktop.sh')]
        if '--check-only' in sys.argv:
            command.append('--check-only')
        return subprocess.call(command)
    except (OSError, ValueError, tarfile.TarError):
        print('No se pudo abrir el instalador. Comprueba el paquete y su archivo SHA256.')
        if sys.stdin.isatty():
            input('Pulsa Enter para cerrar...')
        return 1


if __name__ == '__main__':
    sys.exit(main())
