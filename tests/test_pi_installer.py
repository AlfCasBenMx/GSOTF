import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch, Mock

DEPLOY = Path(__file__).resolve().parents[1] / 'deploy'
sys.path.insert(0, str(DEPLOY))
import pi_installer as installer
import build_release


class InstallerTests(unittest.TestCase):
    def test_stage_progress_does_not_advance_while_waiting_or_on_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            report = installer.Report(temp, 'install')
            report.phase('PYTHON_DEPENDENCIES')
            report.phase('PYTHON_DEPENDENCIES', elapsed=120)
            report.phase('PYTHON_DEPENDENCIES', 'failed', 180)
            data = json.loads((Path(temp) / 'installer-status.json').read_text())
            self.assertEqual(data['progress_percent'], 35)
            self.assertEqual(data['elapsed_seconds'], 180)
            report.phase('PYTHON_DEPENDENCIES', 'completed')
            self.assertEqual(report.progress, 65)
            report.phase('ENVIRONMENT', 'completed')
            self.assertEqual(report.progress, 65)

    def test_full_progress_requires_successful_service_start(self):
        with tempfile.TemporaryDirectory() as temp:
            for command, percent in [('preflight', 5), ('install', 80), ('check', 90), ('start', 100)]:
                report = installer.Report(temp, command)
                report.phase('COMMAND_COMPLETED', 'completed')
                self.assertEqual(report.progress, percent)

    def test_existing_environment_validated_as_service_user(self):
        import types
        with tempfile.TemporaryDirectory() as temp:
            python = Path(temp) / 'python'
            python.touch()
            pwd = types.SimpleNamespace(getpwnam=lambda user: types.SimpleNamespace(pw_dir=temp))
            result = Mock(returncode=0, stdout=b'{"compatible": true}\n')
            with patch.dict(sys.modules, {'pwd': pwd}), patch.object(subprocess, 'run', return_value=result) as command:
                selected = installer.find_environment('pi', installer.Report(temp, 'install'), str(python))
            self.assertEqual(selected, str(python))
            self.assertEqual(command.call_args.args[0][:4], ['runuser', '-u', 'pi', '--'])
            self.assertNotIn('PYTHONNOUSERSITE', command.call_args.kwargs['env'])

    def test_incompatible_explicit_environment_is_rejected(self):
        import types
        with tempfile.TemporaryDirectory() as temp:
            python = Path(temp) / 'python'; python.touch()
            pwd = types.SimpleNamespace(getpwnam=lambda user: types.SimpleNamespace(pw_dir=temp))
            with patch.dict(sys.modules, {'pwd': pwd}), patch.object(subprocess, 'run', return_value=Mock(returncode=1, stdout=b'')):
                with self.assertRaises(installer.Failure):
                    installer.find_environment('pi', installer.Report(temp, 'install'), str(python))

    def test_reused_service_keeps_user_libraries_and_python(self):
        service = installer.unit('gdf-reader.service', '/opt/gdf', 'pi', '/usr/bin/python3', True)
        self.assertIn('ExecStart=/usr/bin/python3 /opt/gdf/MainPlateGSF.py', service)
        self.assertNotIn('PYTHONNOUSERSITE', service)

    def test_step_is_visible_before_command_and_updated_after(self):
        with tempfile.TemporaryDirectory() as temp:
            report = installer.Report(temp, 'install')
            def command(*a, **kw):
                status = json.loads((Path(temp) / 'installer-status.json').read_text())
                self.assertEqual(status['step'], 'VENV')
                self.assertEqual(status['status'], 'running')
                return Mock(returncode=0, stdout=b'private subprocess output')
            with patch.object(subprocess, 'run', side_effect=command):
                installer.run(['fake'], report, 'VENV')
            status = (Path(temp) / 'installer-status.json').read_text()
            self.assertEqual(json.loads(status)['status'], 'completed')
            self.assertNotIn('private subprocess output', status)

    def test_desktop_credentials_do_not_prompt_in_terminal(self):
        values = {'ocrendpoint': 'https://example.invalid', 'ocrKey': 'secret1', 'genyusKey': 'secret2'}
        with patch.object(installer, 'credential_window', return_value=values), patch('builtins.input') as prompt:
            self.assertEqual(installer.credential_values(), values)
            prompt.assert_not_called()

    def test_headless_asks_in_terminal_with_hidden_keys(self):
        with patch.object(installer, 'credential_window', return_value=None), patch.object(sys.stdin, 'isatty', return_value=True), patch('builtins.input', side_effect=['https://example.invalid','Caucel4']), patch('device_identity.check_label', return_value={'checked':True}), patch.object(installer.getpass, 'getpass', side_effect=['secret1', 'secret2']) as hidden:
            values = installer.credential_values()
        self.assertEqual(values['ocrKey'], 'secret1')
        self.assertEqual(hidden.call_count, 2)

    def test_redirected_input_does_not_accept_credentials(self):
        with patch.object(sys.stdin, 'isatty', return_value=False), patch('builtins.input') as prompt:
            with self.assertRaises(installer.Failure):
                installer.credential_values(terminal=True)
            prompt.assert_not_called()

    def test_cancel_does_not_replace_existing_config(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / 'Config.xml'
            config.write_text('<Config><ocrKey>original</ocrKey></Config>')
            args = Mock(root=temp, terminal=False)
            report = installer.Report(temp, 'configure')
            with patch.object(installer, 'require_root'), patch.object(installer, 'credential_values', side_effect=installer.Failure('CONFIG_CANCELLED')):
                with self.assertRaises(installer.Failure):
                    installer.configure(args, report)
            self.assertIn('original', config.read_text())
            self.assertFalse(config.with_suffix('.tmp').exists())

    def test_desktop_form_masks_keys_and_collects_values(self):
        import types
        fields, buttons = [], []
        window = Mock()
        ttk = Mock()
        def entry(*a, **kw):
            field = Mock()
            field.get.return_value = ['https://example.invalid', 'secret1', 'secret2', 'Caucel4'][len(fields)]
            fields.append((field, kw))
            return field
        def button(*a, **kw):
            buttons.append(kw)
            return Mock()
        ttk.Entry.side_effect = entry
        ttk.Button.side_effect = button
        tk = types.ModuleType('tkinter')
        tk.Tk = Mock(return_value=window)
        tk.ttk = ttk
        tk.messagebox = Mock()
        window.mainloop.side_effect = lambda: buttons[-1]['command']()
        with patch.dict(sys.modules, {'tkinter': tk}), patch.dict(installer.os.environ, {'DISPLAY': ':test', 'XAUTHORITY': '/fake'}), patch('device_identity.check_label', return_value={'checked':True}):
            values = installer.credential_window()
        self.assertEqual(values['genyusKey'], 'secret2')
        self.assertEqual([kw['show'] for field, kw in fields], ['', '*', '*', ''])
        tk.messagebox.showerror.assert_not_called()

    def test_partial_start_failure_stops_both_services(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'installation.json').write_text('{"isolated_test": false}')
            args = Mock(root=temp)
            report = installer.Report(temp, 'start')
            def run(command, *a, **kw):
                if command == ['systemctl', 'start', 'gdf-heartbeat.service']:
                    raise installer.Failure('mock_start_failure')
            with patch.object(installer, 'require_root'), patch.object(installer, 'check'), patch.object(installer, 'run', side_effect=run), patch.object(subprocess, 'run') as cleanup:
                with self.assertRaises(installer.Failure):
                    installer.start(args, report)
            self.assertEqual([c.args[0] for c in cleanup.call_args_list],
                             [['systemctl', 'stop', name] for name in installer.UNITS])

    def test_isolated_install_cannot_start_production_services(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'installation.json').write_text('{"isolated_test": true}')
            with patch.object(installer, 'require_root'), patch.object(installer, 'check') as check, patch.object(subprocess, 'run') as system:
                with self.assertRaises(installer.Failure):
                    installer.start(Mock(root=temp), installer.Report(temp, 'start'))
            check.assert_not_called()
            system.assert_not_called()

    def test_failure_report_does_not_copy_process_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            report = installer.Report(temp, 'install')
            result = Mock(returncode=1, stdout=b'No matching distribution; token=SECRET plate=ABC123')
            with patch.object(subprocess, 'run', return_value=result):
                with self.assertRaises(installer.Failure):
                    installer.run(['fake'], report, 'PYTHON_DEPENDENCIES')
            saved = report.save().read_text()
            self.assertIn('package_unavailable', saved)
            self.assertNotIn('SECRET', saved)
            self.assertNotIn('ABC123', saved)

    def test_unexpected_error_report_has_no_exception_text(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(installer, 'diagnose', side_effect=ValueError('SECRET')):
                self.assertEqual(installer.main(['diagnose', '--report-dir', temp]), 1)
            text = next(Path(temp).glob('gdf-diagnostic-*.json')).read_text()
            self.assertIn('UNEXPECTED_ValueError', text)
            self.assertNotIn('SECRET', text)

    def test_manifest_detects_missing_files_traversal_and_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'release-manifest.json').write_text('{}')
            self.assertFalse(installer.verify_manifest(root))
            (root / 'release-manifest.json').write_text(json.dumps({'../secret': 'bad'}))
            self.assertFalse(installer.verify_manifest(root))

    def test_release_allowlist_and_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, model = root / 'src', root / 'model'
            source.mkdir()
            (source / 'deploy').mkdir()
            for name in installer.FILES + ('Config.example.xml', 'Instalar_LIPER.desktop'):
                (source / name).write_text('example')
            for name in ('pi_installer.py', 'pi_probe.py', 'requirements-pi4.txt', 'runtime.example.env', 'INSTALL_PI_ES.md', 'desktop_entry.py', 'install_desktop.sh'):
                (source / 'deploy' / name).write_text('example')
            (source / 'Config.xml').write_text('SECRET')
            (source / 'credentials-local').mkdir()
            (source / 'credentials-local/key').write_text('SECRET')
            variables = model / 'saved_model/variables'
            variables.mkdir(parents=True)
            for name in ('saved_model.pb', 'variables/variables.index', 'variables/variables.data-00000-of-00001'):
                (model / 'saved_model' / name).write_bytes(b'model')
            (model / 'label_map.pbtxt').write_text('label')
            output = root / 'release.tar.gz'
            digest = build_release.build(source, model, output)
            self.assertEqual(digest, hashlib.sha256(output.read_bytes()).hexdigest())
            with tarfile.open(output) as archive:
                names = archive.getnames()
                self.assertFalse(any('credentials-local' in n or n.endswith('/Config.xml') for n in names))
                archive.extractall(root / 'extracted')
            extracted = root / 'extracted/gdf-installer'
            self.assertTrue(installer.verify_manifest(extracted))
            (extracted / 'MainPlateGSF.py').write_text('changed')
            self.assertFalse(installer.verify_manifest(extracted))

    def test_platform_preflight_refuses_other_architecture(self):
        with tempfile.TemporaryDirectory() as temp:
            report = installer.Report(temp, 'preflight')
            with patch.object(installer.platform, 'machine', return_value='x86_64'):
                self.assertFalse(installer.compatibility(report))
            self.assertFalse(next(c['ok'] for c in report.data['checks'] if c['code'] == 'ARM64'))

    def test_generated_service_is_headless_and_uses_venv(self):
        unit = installer.unit('gdf-reader.service', '/opt/gdf', 'pi')
        self.assertIn('ExecStart=/opt/gdf/.venv/bin/python /opt/gdf/MainPlateGSF.py', unit)
        self.assertIn('GDF_DISPLAY=0', unit)
        self.assertIn('EnvironmentFile=-/opt/gdf/runtime.env', unit)
        self.assertNotIn('cleanup', unit)

    def test_path_and_root_service_user_rejected_before_actions(self):
        for args in (['install', '--root', '/opt/../etc'], ['install', '--user', 'root']):
            with self.assertRaises(SystemExit):
                installer.main(args)
