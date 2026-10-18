import hashlib
from pathlib import Path
import shlex
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy'))
import desktop_entry


class DesktopLauncherTests(unittest.TestCase):
    def test_extracted_package_is_used_without_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'release-manifest.json').write_text('{}')
            self.assertEqual(desktop_entry.package_root(root),root)

    def test_repository_package_hash_is_checked_and_unpacked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'releases').mkdir();source=root/'release-manifest.json'
            source.write_text('{}')
            archive=root/'releases/GDF_instalador_pi4.tar.gz'
            with tarfile.open(archive,'w:gz') as t:t.add(source,arcname='gdf-installer/release-manifest.json')
            source.unlink()
            checksum=archive.with_suffix(archive.suffix+'.sha256')
            checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  package\n')
            extracted=desktop_entry.package_root(root)
            self.assertTrue((extracted/'release-manifest.json').is_file())
            import shutil
            shutil.rmtree(extracted.parent)
            checksum.write_text('0'*64+'  package\n')
            with self.assertRaises(ValueError):desktop_entry.package_root(root)

    def test_desktop_exec_handles_uri_and_spaces(self):
        desktop=Path(__file__).resolve().parents[1]/'Instalar_LIPER.desktop'
        line=next(x[5:] for x in desktop.read_text().splitlines() if x.startswith('Exec='))
        parts=shlex.split(line)
        self.assertEqual(parts[:2],['python3','-c'])
        self.assertEqual(parts[-1],'%k')
        with patch.object(sys,'argv',['-c','file:///tmp/folder%20with%20spaces/Instalar_LIPER.desktop']), patch('runpy.run_path') as launch:
            exec(parts[2],{})
        self.assertEqual(Path(launch.call_args.args[0]).name,'desktop_entry.py')
        self.assertIn('folder with spaces',launch.call_args.args[0])
