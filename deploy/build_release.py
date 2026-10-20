"""Build an allowlisted private deployment archive; never include device secrets/photos."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pi_installer import FILES, model_valid


def build(source, model_root, output):
    source, model_root, output = Path(source), Path(model_root), Path(output)
    if not model_valid(model_root):
        raise ValueError('Complete saved_model/ and label_map.pbtxt required')
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp) / 'gdf-installer'
        stage.mkdir()
        for name in FILES + ('Config.example.xml', 'Instalar_LIPER.desktop'):
            shutil.copy2(str(source / name), str(stage / name))
        (stage / 'deploy').mkdir()
        for name in ('pi_installer.py', 'pi_probe.py', 'requirements-pi4.txt', 'runtime.example.env', 'INSTALL_PI_ES.md', 'desktop_entry.py', 'install_desktop.sh', 'open_dashboard.py'):
            shutil.copy2(str(source / 'deploy' / name), str(stage / 'deploy' / name))
        shutil.copytree(str(model_root / 'saved_model'), str(stage / 'saved_model'))
        shutil.copy2(str(model_root / 'label_map.pbtxt'), str(stage / 'label_map.pbtxt'))
        # An explicit model allowlist prevents accidentally packaging arbitrary folder contents.
        for p in (stage / 'saved_model').rglob('*'):
            if p.is_file() and (p.suffix not in ('.pb', '.index') and '.data-' not in p.name):
                p.unlink()
        manifest = {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in stage.rglob('*') if p.is_file()}
        (stage / 'release-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        output.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(str(output), 'w:gz') as archive:
            for p in sorted(stage.rglob('*')):
                if p.is_file():
                    info = archive.gettarinfo(str(p), arcname='gdf-installer/' + p.relative_to(stage).as_posix())
                    info.uid = info.gid = 0
                    info.uname = info.gname = ''
                    info.mode = 0o755 if p.suffix in ('.desktop', '.sh') else 0o644
                    with p.open('rb') as stream:
                        archive.addfile(info, stream)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + '.sha256').write_text(digest + '  ' + output.name + '\n', encoding='ascii')
    return digest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-root', required=True, help='Folder containing saved_model/ and label_map.pbtxt')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(build(Path(__file__).resolve().parents[1], args.model_root, args.output))
