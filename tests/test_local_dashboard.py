import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_dashboard as dashboard


class DashboardTests(unittest.TestCase):
    def test_preview_is_only_requested_by_recent_viewers(self):
        state = dashboard.DashboardState()
        with patch.object(dashboard.time, 'monotonic', return_value=100):
            self.assertFalse(state.wants_preview())
            state.snapshot()
            self.assertTrue(state.wants_preview())
        with patch.object(dashboard.time, 'monotonic', return_value=116):
            self.assertFalse(state.wants_preview())

    def test_installer_creates_desktop_and_login_launchers(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy'))
        import pi_installer
        with tempfile.TemporaryDirectory() as temp, patch.object(pi_installer.os, 'chown', create=True):
            home = Path(temp)
            pi_installer.install_dashboard_launcher(home, Path('/opt/gdf'), 1000, 1000)
            for name in ('.config/autostart/liper-dashboard.desktop', 'Desktop/LIPER-dashboard.desktop'):
                text = (home / name).read_text()
                self.assertIn('Exec=/usr/bin/python3 /opt/gdf/deploy/open_dashboard.py', text)
                self.assertIn('Terminal=false', text)

    def test_keeps_five_distinct_plates_and_refreshes_recrop(self):
        state = dashboard.DashboardState()
        for plate in ('AAA111', 'BBB222', 'CCC333', 'DDD444', 'EEE555', 'FFF666'):
            state.add_plate(plate, b'jpeg')
        self.assertEqual(len(state.snapshot()['plates']), 5)
        state.add_plate('bbb-222', b'new-crop')
        rows = state.snapshot()['plates']
        self.assertEqual([p['plate'] for p in rows], ['BBB222', 'FFF666', 'EEE555', 'DDD444', 'CCC333'])
        self.assertEqual(state.image('/crop/' + rows[0]['id'] + '.jpg'), b'new-crop')
        self.assertNotIn('jpeg', rows[0])

    def test_rejects_empty_and_large_data_and_evicts_images(self):
        state = dashboard.DashboardState()
        state.add_plate('ABC', b'jpeg')
        state.add_plate('ABC123', b'')
        state.add_plate('ABC123', b'x' * (512*1024+1))
        self.assertEqual(state.snapshot()['plates'], [])
        state.add_plate('ABC123', b'jpeg')
        old = state.snapshot()['plates'][0]['id']
        state.add_plate('ABC123', b'updated')
        self.assertIsNone(state.image('/crop/' + old + '.jpg'))
        state.set_frame(b'frame')
        state.set_frame(b'x' * (512*1024+1))
        self.assertEqual(state.image('/frame.jpg'), b'frame')

    def test_http_only_serves_preview_and_bounded_readings(self):
        state = dashboard.DashboardState()
        state.set_frame(b'jpeg-frame')
        state.add_plate('ABC123', b'jpeg-crop')
        server = dashboard.start(port=0, state=state)
        base = 'http://127.0.0.1:%d' % server.server_port
        try:
            self.assertEqual(server.server_address[0], '127.0.0.1')
            with urllib.request.urlopen(base + '/api/state') as response:
                data = json.load(response)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            with urllib.request.urlopen(base + '/frame.jpg') as response:
                self.assertEqual(response.read(), b'jpeg-frame')
            with urllib.request.urlopen(base + '/crop/' + data['plates'][0]['id'] + '.jpg') as response:
                self.assertEqual(response.read(), b'jpeg-crop')
            with urllib.request.urlopen(base) as response:
                self.assertIn(b'textContent', response.read())
            for path in ('/Config.xml', '/runtime.env', '/../Config.xml'):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base + path)
                self.assertEqual(error.exception.code, 404)
            request = urllib.request.Request(base, headers={'Host': 'evil.example'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            self.assertEqual(error.exception.code, 403)
        finally:
            dashboard.ACTIVE.clear()
            server.shutdown()
            server.server_close()

    def test_disabled_panel_does_not_decode_or_load_native_libraries(self):
        dashboard.ACTIVE.clear()
        with patch.dict(sys.modules, {'cv2': None, 'numpy': None}):
            dashboard.record_reading(['ABC123'], b'crop')

    def test_desktop_launcher_waits_for_service_before_browser(self):
        import importlib.util
        path = Path(__file__).resolve().parents[1] / 'deploy/open_dashboard.py'
        spec = importlib.util.spec_from_file_location('open_dashboard', path)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.status = 200
        with patch.object(launcher.urllib.request, 'urlopen', side_effect=[OSError(), response]), patch.object(launcher.time, 'sleep'), patch.object(launcher.webbrowser, 'open') as browser:
            self.assertEqual(launcher.main(), 0)
            browser.assert_called_once_with('http://127.0.0.1:8765/')


if __name__ == '__main__':
    unittest.main()
