#!/usr/bin/env python3
"""Fresh Pi installations only. Standard-library bootstrap and private diagnostics."""
import argparse
import datetime
import getpass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
FILES = ('MainPlateGSF.py', 'MainHBGSF.py', 'LiPER_NNP.py', 'Send_HB.py',
         'StartSettings.py', 'HandlingEvents.py', 'runtime.py',
         'SendNotifications.py', 'ocr_evidence.py', 'device_identity.py', 'local_dashboard.py')
UNITS = ('gdf-reader.service', 'gdf-heartbeat.service')
STEPS = {
    'COMMAND_STARTED': 'Iniciando etapa de instalacion',
    'COMMAND_COMPLETED': 'Etapa completada correctamente',
    'APT_INDEX': 'Actualizar lista de paquetes del sistema',
    'APT_DEPENDENCIES': 'Instalar librerias del sistema y de la camara',
    'VENV': 'Crear entorno de Python',
    'PIP_BOOTSTRAP': 'Preparar herramientas de instalacion de Python',
    'PYTHON_DEPENDENCIES': 'Descargar e instalar librerias, incluido TensorFlow',
    'DETECTION_UTILITIES': 'Instalar utilidades de deteccion',
    'CAMERA_GROUPS': 'Configurar acceso a la camara',
    'SYSTEMD_RELOAD': 'Registrar servicios',
    'IMPORTS': 'Comprobar importacion de librerias',
    'MODEL': 'Cargar y comprobar modelo de deteccion',
    'CAMERA': 'Comprobar captura de camara',
    'CREDENTIALS': 'Esperando que ingreses las credenciales',
    'ENVIRONMENT': 'Buscar un entorno existente compatible',
}


class Failure(Exception):
    pass


class Report:
    def __init__(self, folder, command):
        self.folder = Path(folder)
        self.data = {'schema': 1, 'command': command, 'utc': datetime.datetime.now(
            datetime.timezone.utc).isoformat(), 'checks': []}
        self.progress = {'preflight': 0, 'install': 5, 'configure': 75,
                         'check': 80, 'start': 90, 'diagnose': 0}.get(command, 0)

    def percentage(self, code, state):
        ranges = {'ENVIRONMENT': (5, 10), 'APT_INDEX': (10, 15),
                  'APT_DEPENDENCIES': (15, 25), 'VENV': (25, 30),
                  'PIP_BOOTSTRAP': (30, 35), 'PYTHON_DEPENDENCIES': (35, 65),
                  'DETECTION_UTILITIES': (65, 70), 'CAMERA_GROUPS': (70, 72),
                  'SYSTEMD_RELOAD': (72, 75), 'CREDENTIALS': (75, 80),
                  'IMPORTS': (80, 83), 'MODEL': (83, 86), 'CAMERA': (86, 89)}
        if code == 'COMMAND_COMPLETED' and state == 'completed':
            target = {'preflight': 5, 'install': 80, 'configure': 80,
                      'check': 90, 'start': 100, 'diagnose': 100}[self.data['command']]
        else:
            bounds = ranges.get(code, (self.progress, self.progress))
            target = bounds[1] if state == 'completed' else bounds[0]
        self.progress = max(self.progress, target)
        return self.progress

    def phase(self, code, state='running', elapsed=0):
        label = STEPS.get(code, code)
        seconds = int(elapsed)
        percent = self.percentage(code, state)
        print('[%s] %d%% | %s | %dm %02ds (avance por etapas)' %
              (state.upper(), percent, label, seconds // 60, seconds % 60), flush=True)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        value = dict(command=self.data['command'], step=code, label=label,
                     status=state, elapsed_seconds=seconds,
                     progress_percent=percent, progress_basis='installation_stages',
                     updated_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        temporary = self.folder / 'installer-status.tmp'
        with temporary.open('w', encoding='utf-8') as stream:
            os.chmod(str(temporary), 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(str(temporary), str(self.folder / 'installer-status.json'))

    def add(self, code, ok, action='', detail=''):
        # Callers supply only controlled text, never raw exceptions or subprocess output.
        self.data['checks'].append(dict(code=code, ok=bool(ok), action=action, detail=detail))
        print(('OK   ' if ok else 'FAIL ') + code + (': ' + action if not ok else ''), flush=True)

    def save(self):
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.folder / ('gdf-diagnostic-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
        with path.open('x', encoding='utf-8') as f:
            os.chmod(str(path), 0o600)
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        print('REPORT=' + str(path), flush=True)
        return path


def run(args, report, code, timeout=180, env=None):
    started = time.monotonic()
    finished = threading.Event()
    report.phase(code)
    def heartbeat():
        while not finished.wait(30):
            try:
                report.phase(code, elapsed=time.monotonic() - started)
            except OSError:
                print('No se pudo actualizar el archivo de progreso.', flush=True)
    ticker = threading.Thread(target=heartbeat, daemon=True)
    ticker.start()
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout, env=env)
        ok = result.returncode == 0
        detail = 'exit=' + str(result.returncode)
        if not ok:
            # Classify output without copying it: pip and SDK traces may contain URLs/secrets.
            text = result.stdout.decode('utf-8', errors='replace').lower()
            for needle, category in (('no matching distribution', 'package_unavailable'),
                                     ('resolutionimpossible', 'dependency_conflict'),
                                     ('failed building wheel', 'native_build_failed'),
                                     ('temporary failure resolving', 'dns_failed'),
                                     ('certificate_verify_failed', 'tls_failed'),
                                     ('no space left', 'disk_full'),
                                     ('modulenotfounderror', 'missing_module'),
                                     ('permission denied', 'permission_denied'),
                                     ('device or resource busy', 'device_busy')):
                if needle in text:
                    detail += ';category=' + category
                    break
    except subprocess.TimeoutExpired:
        ok, detail = False, 'timeout'
    except OSError:
        ok, detail = False, 'executable unavailable'
    finally:
        finished.set()
        ticker.join()
    report.phase(code, 'completed' if ok else 'failed', time.monotonic() - started)
    report.add(code, ok, 'Repeat this step manually on the device; then run diagnose.', detail)
    if not ok:
        raise Failure(code)


def compatibility(report):
    try:
        model = Path('/proc/device-tree/model').read_text().strip('\0')
        os_data = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    except OSError:
        model, os_data = '', {}
    checks = [('PI4', model.startswith('Raspberry Pi 4 Model B'), 'Use Raspberry Pi 4 Model B.'),
              ('ARM64', platform.machine() == 'aarch64', 'Use a 64-bit OS image.'),
              ('BULLSEYE', os_data.get('VERSION_ID', '').strip('"') == '11', 'Use the Bullseye 64-bit reference image; other OS versions need separate validation.'),
              ('PYTHON39', sys.version_info[:2] == (3, 9), 'Use Python 3.9 from the reference OS.')]
    for code, ok, action in checks:
        report.add(code, ok, action)
    return all(c[1] for c in checks)


def model_valid(source):
    folder = Path(source)
    return ((folder / 'saved_model/saved_model.pb').is_file()
            and (folder / 'saved_model/variables/variables.index').is_file()
            and any((folder / 'saved_model/variables').glob('variables.data-*'))
            and (folder / 'label_map.pbtxt').is_file())


def verify_manifest(source):
    source = Path(source)
    try:
        entries = json.loads((source / 'release-manifest.json').read_text())
        if not isinstance(entries, dict) or not entries:
            return False
        for name, expected in entries.items():
            p = (source / name).resolve()
            if source.resolve() not in p.parents or not p.is_file():
                return False
            if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
                return False
        required = set(FILES) | {'Config.example.xml', 'Instalar_LIPER.desktop', 'deploy/desktop_entry.py',
                                  'deploy/install_desktop.sh', 'deploy/open_dashboard.py', 'deploy/runtime.example.env',
                                  'deploy/pi_probe.py', 'deploy/pi_installer.py', 'deploy/requirements-pi4.txt',
                                  'label_map.pbtxt', 'saved_model/saved_model.pb',
                                  'saved_model/variables/variables.index'}
        return required.issubset(entries) and all(
            p.relative_to(source).as_posix() in entries for p in (source / 'saved_model').rglob('*') if p.is_file())
    except (OSError, ValueError, TypeError):
        return False


def require_root():
    if not hasattr(os, 'geteuid') or os.geteuid() != 0:
        raise Failure('ROOT_REQUIRED: use sudo')


def unit(name, root, user, python=None, include_user_site=False):
    main = 'MainPlateGSF.py' if name == 'gdf-reader.service' else 'MainHBGSF.py'
    python = python or root + '/.venv/bin/python'
    return f'''[Unit]
Description=GDF {name}
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=600
StartLimitBurst=3
[Service]
Type=simple
User={user}
WorkingDirectory={root}
Environment=GDF_DISPLAY=0
Environment=GDF_CONFIG={root}/Config.xml
Environment=PYTHONUNBUFFERED=1
{'' if include_user_site else 'Environment=PYTHONNOUSERSITE=1'}
EnvironmentFile=-{root}/runtime.env
ExecStart={python} {root}/{main}
Restart=on-failure
RestartSec=15
TimeoutStopSec=180
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target
'''


def find_environment(user, report, explicit=None):
    import pwd
    account = pwd.getpwnam(user)
    home = Path(account.pw_dir)
    candidates = ([Path(explicit)] if explicit else [SOURCE / '.venv/bin/python',
        home / '.venvs/gdf/bin/python', home / 'Desktop/GDF/.venv/bin/python',
        Path('/opt/gdf/.venv/bin/python'), Path('/usr/bin/python3')])
    started = time.monotonic()
    report.phase('ENVIRONMENT')
    env = dict(os.environ, HOME=str(home), USER=user)
    env.pop('PYTHONNOUSERSITE', None)
    env.pop('PYTHONPATH', None)
    for number, python in enumerate(candidates, 1):
        if not python.is_file():
            continue
        command = ['runuser', '-u', user, '--', str(python), str(SOURCE / 'deploy/pi_probe.py'), 'environment', str(SOURCE)]
        try:
            result = subprocess.run(command, capture_output=True, timeout=180, env=env)
            valid = result.returncode == 0 and any(
                line.strip().startswith(b'{') and json.loads(line).get('compatible') is True
                for line in result.stdout.splitlines() if line.strip().startswith(b'{'))
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            valid = False
        report.add('ENVIRONMENT_CANDIDATE_' + str(number), valid,
                   'This environment is unsuitable; continue searching or create a new one.')
        if valid:
            report.phase('ENVIRONMENT', 'completed', time.monotonic() - started)
            return str(python)
    report.phase('ENVIRONMENT', 'not_found', time.monotonic() - started)
    if explicit:
        raise Failure('EXPLICIT_ENVIRONMENT_INCOMPATIBLE')
    return None


def install_dashboard_launcher(home, root, uid, gid):
    # This runs in the user's graphical login, independently of the reader service.
    for folder in (home / '.config', home / '.config/autostart', home / 'Desktop'):
        if not folder.exists():
            folder.mkdir(parents=True, mode=0o700)
            os.chown(str(folder), uid, gid)
    text = ('[Desktop Entry]\nType=Application\nName=LIPER - Camara y lecturas\n'
            'Exec=/usr/bin/python3 ' + (root / 'deploy/open_dashboard.py').as_posix() + '\n'
            'Terminal=false\nIcon=camera-video\n')
    for target in (home / '.config/autostart/liper-dashboard.desktop', home / 'Desktop/LIPER-dashboard.desktop'):
        target.write_text(text, encoding='utf-8')
        target.chmod(0o755)
        os.chown(str(target), uid, gid)


def install(args, report):
    require_root()
    import pwd
    root = Path(args.root)
    if not compatibility(report):
        raise Failure('INCOMPATIBLE_PLATFORM')
    report.add('FRESH_TARGET', not root.exists(), 'Choose a new directory; this installer does not update production.')
    if root.exists():
        raise Failure('TARGET_EXISTS')
    report.add('RELEASE_HASHES', verify_manifest(SOURCE), 'Obtain a complete release package and verify its checksum.')
    report.add('MODEL_FILES', model_valid(SOURCE), 'Include saved_model and label_map.pbtxt in the release.')
    free = shutil.disk_usage(str(root.parent)).free
    report.add('DISK_8GB', free >= 8 * 1024**3, 'Free at least 8 GiB before installing.')
    if not all(c['ok'] for c in report.data['checks']):
        raise Failure('PREFLIGHT_FAILED')
    account = pwd.getpwnam(args.user)
    isolated = args.isolated_test
    if not isolated:
        for name in UNITS:
            if Path('/etc/systemd/system', name).exists():
                raise Failure('EXISTING_SERVICE: use a fresh device; existing services were preserved')
    selected_python = None if args.fresh_env else find_environment(args.user, report, args.python)
    if selected_python:
        report.add('REUSE_ENVIRONMENT', True, detail='Imports and reference runtime versions validated as service user; no pip or apt changes.')
    elif isolated:
        import importlib.util
        available = all(importlib.util.find_spec(n) is not None for n in ('venv', 'pip', 'picamera2', 'libcamera', 'serial', 'psutil', 'tkinter'))
        report.add('EXISTING_SYSTEM_LIBRARIES', available, 'Install missing OS libraries separately before the isolated test.')
        if not available:
            raise Failure('MISSING_SYSTEM_LIBRARIES')
    else:
        for name in UNITS:
            if Path('/etc/systemd/system', name).exists():
                raise Failure('EXISTING_SERVICE: use a fresh device; existing services were preserved')
        apt_env = dict(os.environ, DEBIAN_FRONTEND='noninteractive')
        run(['apt-get', 'update'], report, 'APT_INDEX', timeout=600, env=apt_env)
        run(['apt-get', 'install', '-y', 'python3-venv', 'python3-pip', 'python3-picamera2',
             'python3-libcamera', 'python3-serial', 'python3-psutil', 'python3-tk', 'build-essential', 'python3-dev',
             'libjpeg-dev', 'zlib1g-dev', 'libxml2-dev', 'libxslt1-dev', 'libopenblas-dev',
             'libhdf5-dev', 'pkg-config', 'libgl1', 'libglib2.0-0'], report, 'APT_DEPENDENCIES', timeout=1800, env=apt_env)
    root.mkdir(mode=0o750)
    # State is explicit; failed installs can be diagnosed and inspected without enabling services.
    (root / 'installation.json').write_text(json.dumps({'state': 'preparing', 'user': args.user}))
    for name in FILES:
        shutil.copy2(str(SOURCE / name), str(root / name))
    shutil.copytree(str(SOURCE / 'deploy'), str(root / 'deploy'))
    shutil.copytree(str(SOURCE / 'saved_model'), str(root / 'saved_model'))
    shutil.copy2(str(SOURCE / 'label_map.pbtxt'), str(root / 'label_map.pbtxt'))
    python = selected_python or str(root / '.venv/bin/python')
    env = dict(os.environ, PYTHONNOUSERSITE='1', PIP_DISABLE_PIP_VERSION_CHECK='1',
               PIP_CONFIG_FILE=os.devnull, PIP_INDEX_URL='https://pypi.org/simple',
               PIP_EXTRA_INDEX_URL='', PIP_TIMEOUT='20', PIP_RETRIES='1', PIP_NO_INPUT='1')
    if not selected_python:
        run(['python3', '-m', 'venv', '--system-site-packages', str(root / '.venv')], report, 'VENV')
        pip = ['nice', '-n', '19', 'ionice', '-c', '2', '-n', '7', python, '-m', 'pip']
        run(pip + ['install', '--no-compile', 'pip==24.0', 'setuptools==69.5.1', 'wheel==0.43.0'], report, 'PIP_BOOTSTRAP', timeout=600, env=env)
        run(pip + ['install', '--no-compile', '--prefer-binary', '-r', str(root / 'deploy/requirements-pi4.txt')], report, 'PYTHON_DEPENDENCIES', timeout=3600, env=env)
    # This legacy package declares notebook/publishing tools and a second TensorFlow distribution.
    # Only its runtime utilities are used; install it separately to avoid those extra dependencies.
        run(pip + ['install', '--no-compile', '--no-deps', 'tensorflow-object-detection-api==0.1.1'], report, 'DETECTION_UTILITIES', timeout=600, env=env)
    for name in ('SavedPlates', 'ErrorOCR', 'OCREvidence', 'Logs', 'TempImages', 'PlateRegionImage', 'TempSavedImages'):
        (root / name).mkdir(exist_ok=True)
    shutil.copy2(str(SOURCE / 'Config.example.xml'), str(root / 'Config.xml'))
    shutil.copy2(str(SOURCE / 'deploy/runtime.example.env'), str(root / 'runtime.env'))
    for p in (root / 'Config.xml', root / 'runtime.env'):
        p.chmod(0o600)
    shutil.chown(str(root), account.pw_uid, account.pw_gid)
    for folder, dirs, files in os.walk(str(root)):
        for name in dirs + files:
            os.chown(os.path.join(folder, name), account.pw_uid, account.pw_gid)
    # Camera access is granted explicitly; do not change unrelated groups.
    import grp
    groups = [g for g in ('video', 'render') if any(x.gr_name == g for x in grp.getgrall())]
    if groups and not isolated:
        run(['usermod', '-a', '-G', ','.join(groups), args.user], report, 'CAMERA_GROUPS')
    if not isolated:
        for name in UNITS:
            Path('/etc/systemd/system', name).write_text(unit(name, str(root), args.user, python, bool(selected_python)))
        run(['systemctl', 'daemon-reload'], report, 'SYSTEMD_RELOAD')
        install_dashboard_launcher(Path(account.pw_dir), root, account.pw_uid, account.pw_gid)
        report.add('DASHBOARD_DESKTOP', True)
    (root / 'installation.json').write_text(json.dumps({'state': 'installed_not_started', 'user': args.user, 'isolated_test': isolated,
                                                      'python': python, 'reuse_environment': bool(selected_python)}))
    report.add('INSTALLED_NOT_STARTED', True, detail='Configure credentials, run check --hardware, then start. Cleanup not installed.')
    if not args.skip_config:
        configure(args, report)


DEFAULT_HEALTH_URL = 'https://liper-health-monitor.loftygrebe10.chatgpt.site/api/heartbeat'

def validate_monitor(url, token):
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or any(c.isspace() for c in url):
        raise ValueError('Escribe una URL HTTPS valida para el monitor.')
    if not token or any(c.isspace() for c in token):
        raise ValueError('Introduce el token del monitor sin espacios.')


def credential_window(initial_label='', health_url='', health_token=''):
    """Return None only when a desktop cannot be opened; cancellation is explicit."""
    if not os.environ.get('DISPLAY') and sys.platform != 'win32':
        return None
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
        # sudo may drop XAUTHORITY while retaining DISPLAY on the reference desktop.
        if os.environ.get('SUDO_USER') and not os.environ.get('XAUTHORITY'):
            import pwd
            authority = Path(pwd.getpwnam(os.environ['SUDO_USER']).pw_dir) / '.Xauthority'
            if authority.is_file():
                os.environ['XAUTHORITY'] = str(authority)
        window = tk.Tk()
    except (ImportError, OSError, KeyError):
        return None
    except Exception as error:
        if type(error).__name__ == 'TclError':
            return None
        raise
    window.title('GDF - Configurar credenciales')
    window.resizable(False, False)
    panel = ttk.Frame(window, padding=24)
    panel.grid()
    ttk.Label(panel, text='Configura esta Raspberry', font=('Arial', 14, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 12))
    ttk.Label(panel, text='Las claves se guardan solo en este equipo.').grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 12))
    entries = {}
    for row, (key, label, secret) in enumerate((('ocrendpoint', 'Endpoint HTTPS de Azure OCR', False),
                                               ('ocrKey', 'Clave de Azure OCR', True),
                                               ('genyusKey', 'Clave de Genyus', True),
                                               ('device_label', 'Nombre del equipo (monitor)', False),
                                               ('health_url', 'URL HTTPS del monitor', False),
                                               ('health_token', 'Token del monitor', True)), start=2):
        ttk.Label(panel, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=8)
        entry = ttk.Entry(panel, width=48, show='*' if secret else '')
        entry.grid(row=row, column=1, pady=8)
        entries[key] = entry
        if key == 'device_label' and initial_label:
            entry.insert(0, initial_label)
        if key == 'health_url':
            entry.insert(0, health_url or DEFAULT_HEALTH_URL)
        if key == 'health_token' and health_token:
            entry.insert(0, health_token)
    result = []
    def save():
        values = {key: field.get().strip() for key, field in entries.items()}
        if not re.fullmatch(r'https://[A-Za-z0-9.-]+/?', values['ocrendpoint']):
            messagebox.showerror('Revisa el endpoint', 'Escribe una URL HTTPS sin rutas, consultas ni credenciales.', parent=window)
            return
        if not all(values.values()):
            messagebox.showerror('Faltan datos', 'Completa los seis campos.', parent=window)
            return
        import device_identity
        try:
            validate_monitor(values['health_url'], values['health_token'])
            values['device_label'] = device_identity.clean_label(values['device_label'])
            window.configure(cursor='watch')
            window.update_idletasks()
            device_identity.check_label(values['device_label'], values['health_url'])
            values['_name_validated'] = True
        except device_identity.NameTaken:
            messagebox.showerror('Nombre ocupado', 'Otra Raspberry ya usa ese nombre. Elige otro.', parent=window)
            return
        except device_identity.NameCheckUnavailable:
            if not messagebox.askyesno('Nombre sin validar', 'No se pudo consultar el monitor. La unicidad NO esta confirmada. Guardar localmente sin validarla?', parent=window):
                return
            values['_name_validated'] = False
        except ValueError as error:
            messagebox.showerror('Nombre no valido', str(error), parent=window)
            return
        finally:
            window.configure(cursor='')
        result.append(values)
        window.destroy()
    ttk.Label(panel, text='Nombre: 3-40 letras, numeros, espacios, guion o guion bajo.').grid(row=8, column=0, columnspan=2, sticky='w')
    ttk.Button(panel, text='Cancelar', command=window.destroy).grid(row=9, column=0, pady=(18, 0), sticky='w')
    ttk.Button(panel, text='Guardar', command=save).grid(row=9, column=1, pady=(18, 0), sticky='e')
    window.bind('<Return>', lambda event: save())
    window.bind('<Escape>', lambda event: window.destroy())
    entries['ocrendpoint'].focus_set()
    window.mainloop()
    if not result:
        raise Failure('CONFIG_CANCELLED: software installed; configure later before starting')
    return result[0]


def credential_values(terminal=False, initial_label='', health_url='', health_token=''):
    if not terminal:
        values = credential_window(initial_label=initial_label, health_url=health_url, health_token=health_token)
        if values is not None:
            return values
        print('No desktop available; enter credentials in the terminal.', flush=True)
    if not sys.stdin.isatty():
        raise Failure('INTERACTIVE_TERMINAL_REQUIRED: run configure in a desktop or interactive terminal')
    endpoint = input('Azure OCR HTTPS endpoint: ').strip()
    if not re.fullmatch(r'https://[A-Za-z0-9.-]+/?', endpoint):
        raise Failure('INVALID_OCR_ENDPOINT')
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            values = {'ocrendpoint': endpoint, 'ocrKey': getpass.getpass('Azure OCR key: ').strip(),
                      'genyusKey': getpass.getpass('Genyus key: ').strip(),
                      'health_token': getpass.getpass('Monitor token (Enter keeps existing): ').strip() or health_token}
        except getpass.GetPassWarning:
            raise Failure('SECURE_INPUT_UNAVAILABLE: use an interactive terminal with echo control')
    if not all(values.values()):
        raise Failure('EMPTY_CREDENTIAL')
    values['health_url'] = input('Monitor HTTPS URL (Enter uses default): ').strip() or health_url or DEFAULT_HEALTH_URL
    validate_monitor(values['health_url'], values['health_token'])
    import device_identity
    values['device_label'] = device_identity.clean_label(input('Nombre del equipo para el monitor: ').strip() or initial_label)
    try:
        device_identity.check_label(values['device_label'], values['health_url'])
        values['_name_validated'] = True
    except device_identity.NameTaken:
        raise Failure('DEVICE_NAME_TAKEN: elige otro nombre')
    except device_identity.NameCheckUnavailable:
        print('No se pudo validar la unicidad en el monitor.')
        if input('Guardar localmente sin validar? [s/N]: ').strip().lower() != 's':
            raise Failure('DEVICE_NAME_NOT_VALIDATED')
        values['_name_validated'] = False
    return values


def configure(args, report):
    require_root()
    path = Path(args.root) / 'Config.xml'
    tree = ET.parse(str(path))
    report.phase('CREDENTIALS', 'waiting_for_input')
    sys.path.insert(0, str(SOURCE))
    import device_identity
    runtime = device_identity.runtime_values(Path(args.root) / 'runtime.env')
    try:
        values = credential_values(terminal=args.terminal, initial_label=runtime.get('GDF_HEALTH_LABEL', ''), health_url=runtime.get('GDF_HEALTH_URL', ''), health_token=runtime.get('GDF_HEALTH_TOKEN', ''))
    except (Exception, KeyboardInterrupt):
        report.phase('CREDENTIALS', 'failed')
        raise
    label = values.pop('device_label')
    validated = values.pop('_name_validated')
    monitor_url = values.pop('health_url')
    monitor_token = values.pop('health_token')
    validate_monitor(monitor_url, monitor_token)
    for tag, value in values.items():
        node = tree.getroot().find(tag)
        if node is None:
            node = ET.SubElement(tree.getroot(), tag)
        node.text = value
    temporary = path.with_suffix('.tmp')
    with temporary.open('wb') as stream:
        os.chmod(str(temporary), 0o600)
        tree.write(stream, encoding='utf-8', xml_declaration=True)
    owner = path.stat()
    os.chown(str(temporary), owner.st_uid, owner.st_gid)
    os.replace(str(temporary), str(path))
    device_identity.save_monitor(Path(args.root) / 'runtime.env', {
        'GDF_HEALTH_LABEL': label, 'GDF_HEALTH_URL': monitor_url, 'GDF_HEALTH_TOKEN': monitor_token})
    report.add('CONFIG_SAVED', True)
    report.add('DEVICE_NAME_CHECKED', validated, 'Nombre guardado localmente; unicidad central no confirmada.' if not validated else '', detail='Availability check is not a reservation; server rejects duplicate registered names.')
    report.phase('CREDENTIALS', 'completed')


def probe(args, report, kind):
    root = Path(args.root)
    state = json.loads((root / 'installation.json').read_text())
    # Run native-library/model probes as the service account, never root or the active reader.
    command = [state.get('python', str(root / '.venv/bin/python')), str(root / 'deploy/pi_probe.py'), kind, str(root)]
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        command = ['runuser', '-u', state['user'], '--'] + command
    env = dict(os.environ, GDF_CONFIG=str(root / 'Config.xml'))
    if state.get('reuse_environment'):
        env.pop('PYTHONNOUSERSITE', None)
    else:
        env['PYTHONNOUSERSITE'] = '1'
    run(command, report, kind.upper(), timeout=240, env=env)


def check(args, report):
    ok = compatibility(report)
    root = Path(args.root)
    report.add('MODEL_FILES', model_valid(root), 'Restore the complete model and labels from the release.')
    config_ok = False
    endpoint = ''
    try:
        xml = ET.parse(str(root / 'Config.xml')).getroot()
        config_ok = all((xml.findtext(k) or '').strip() for k in ('ocrKey', 'genyusKey', 'ocrendpoint'))
        endpoint = (xml.findtext('ocrendpoint') or '').strip()
        config_ok = config_ok and bool(re.fullmatch(r'https://[A-Za-z0-9.-]+/?', endpoint))
    except (OSError, ET.ParseError):
        pass
    report.add('CONFIG_REQUIRED', config_ok, 'Run configure on the device; never put credentials in a report.')
    for name in ('Config.xml', 'runtime.env'):
        try:
            private = (root / name).stat().st_mode & 0o077 == 0
        except OSError:
            private = False
        report.add('PRIVATE_' + name.upper(), private, 'Set file owner to the service user and permissions to 600.')
    free = shutil.disk_usage(str(root if root.exists() else root.parent)).free
    report.add('DISK_2GB', free >= 2 * 1024**3, 'Free disk space without deleting evidence automatically.')
    for label, host in [('GENYUS', 'uat-genyus.ey.com'), ('AZURE', endpoint.removeprefix('https://').rstrip('/'))]:
        network_ok = False
        if host and re.fullmatch('[A-Za-z0-9.-]+', host):
            try:
                with socket.create_connection((host, 443), timeout=8) as sock:
                    with ssl.create_default_context().wrap_socket(sock, server_hostname=host):
                        network_ok = True
            except (OSError, ValueError):
                pass
        report.add(label + '_TLS', network_ok, 'Check Internet, DNS, system clock and destination firewall. This does not validate API credentials.')
    if args.hardware:
        probe(args, report, 'imports')
        probe(args, report, 'model')
        for name in UNITS[:1]:
            active = subprocess.run(['systemctl', 'is-active', '--quiet', name]).returncode == 0
            if active:
                report.add('CAMERA_IDLE', False, 'Stop the reader before a hardware camera test.')
                raise Failure('CAMERA_BUSY')
        probe(args, report, 'camera')
    if not ok or not all(c['ok'] for c in report.data['checks']):
        raise Failure('CHECK_FAILED')


def start(args, report):
    require_root()
    state = json.loads((Path(args.root) / 'installation.json').read_text())
    if state.get('isolated_test'):
        raise Failure('ISOLATED_TEST: services cannot be started from this test installation')
    args.hardware = True
    check(args, report)
    enabled = []
    try:
        for name in UNITS:
            run(['systemctl', 'start', name], report, 'START_' + name)
        root = Path(args.root)
        deadline = time.monotonic() + 180
        healthy = False
        while time.monotonic() < deadline:
            try:
                health = json.loads((root / '.health.json').read_text())
                pid = subprocess.check_output(['systemctl', 'show', 'gdf-reader.service', '--property=MainPID', '--value'], text=True).strip()
                if str(health['pid']) == pid and 0 <= time.time() - health['last_frame'] < 30:
                    healthy = True
                    break
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                pass
            time.sleep(3)
        report.add('FIRST_FRAME', healthy, 'Run diagnose; reader did not produce a current frame within 180 seconds.')
        if not healthy:
            raise Failure('START_NO_FRAME')
        run(['systemctl', 'is-active', '--quiet', 'gdf-heartbeat.service'], report, 'HEARTBEAT_ACTIVE')
        for name in UNITS:
            run(['systemctl', 'enable', name], report, 'ENABLE_' + name)
            enabled.append(name)
    except (Exception, KeyboardInterrupt):
        for name in UNITS:
            subprocess.run(['systemctl', 'stop', name], timeout=190)
        for name in enabled:
            subprocess.run(['systemctl', 'disable', name], timeout=30)
        raise


def diagnose(args, report):
    compatibility(report)
    root = Path(args.root)
    report.add('MODEL_FILES', model_valid(root), 'Restore model from release.')
    for name in UNITS:
        try:
            result = subprocess.run(['systemctl', 'show', name, '-p', 'ActiveState', '-p', 'NRestarts', '-p', 'Result'], capture_output=True, text=True, timeout=10)
            # Strict allowlist excludes command lines, environment, logs, network and device IDs.
            fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            report.add('SERVICE_' + name, fields.get('ActiveState') == 'active',
                       'Inspect this service locally with journalctl.',
                       ';'.join(k + '=' + fields.get(k, 'unknown') for k in ('ActiveState', 'NRestarts', 'Result')))
        except (OSError, subprocess.SubprocessError):
            report.add('SERVICE_' + name, False, 'systemctl unavailable')
    try:
        health = json.loads((root / '.health.json').read_text())
        age = round(time.time() - float(health['last_frame']), 1)
        report.add('FRAME_FRESH', 0 <= age <= 30, 'Inspect reader/camera/model locally.', 'age_seconds=' + str(age))
    except (OSError, ValueError, KeyError, TypeError):
        report.add('FRAME_FRESH', False, 'No frame health file yet.')
    try:
        temp = int(Path('/sys/class/thermal/thermal_zone0/temp').read_text()) / 1000
        report.add('TEMPERATURE_UNDER_80', temp < 80, 'Check cooling.', 'celsius=' + str(temp))
    except (OSError, ValueError):
        pass
    if root.exists():
        free = shutil.disk_usage(str(root)).free
        report.add('DISK_2GB', free >= 2 * 1024**3, 'Review storage manually.', 'free_bytes=' + str(free))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'install', 'configure', 'check', 'start', 'diagnose'))
    parser.add_argument('--root', default='/opt/gdf')
    parser.add_argument('--user', default='pi')
    parser.add_argument('--report-dir', default='./gdf-reports')
    parser.add_argument('--hardware', action='store_true', help='Imports, model load and idle camera capture; never sends plates.')
    parser.add_argument('--terminal', action='store_true', help='Ask for credentials in the terminal instead of a desktop window.')
    parser.add_argument('--skip-config', action='store_true', help='Install without interactive credential entry; configure later.')
    parser.add_argument('--isolated-test', action='store_true', help='Use existing OS libraries; install only into a new folder, without services or system changes.')
    parser.add_argument('--fresh-env', action='store_true', help='Create a new Python environment even if an existing one is compatible.')
    parser.add_argument('--python', help='Validate and reuse this Python executable; fails if incompatible.')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'/[A-Za-z0-9_/-]+', args.root) or '..' in Path(args.root).parts or args.root == '/':
        parser.error('root must be a simple absolute dedicated directory')
    if not re.fullmatch('[a-z_][a-z0-9_-]*', args.user) or args.user == 'root':
        parser.error('invalid service user')
    if args.python and (not re.fullmatch(r'/[A-Za-z0-9_./-]+', args.python) or '..' in Path(args.python).parts):
        parser.error('python must be a simple absolute executable path')
    if args.python and args.fresh_env:
        parser.error('--python and --fresh-env cannot be combined')
    report = Report(args.report_dir, args.command)
    status = 0
    try:
        report.phase('COMMAND_STARTED')
        if args.command == 'preflight':
            if not compatibility(report):
                raise Failure('INCOMPATIBLE_PLATFORM')
        else:
            globals()[args.command](args, report)
        report.phase('COMMAND_COMPLETED', 'completed')
    except KeyboardInterrupt:
        report.add('INTERRUPTED', False, 'Run diagnose before retrying.')
        status = 130
    except Failure as error:
        report.add('STOPPED', False, str(error))
        status = 1
    except Exception as error:
        report.add('UNEXPECTED_' + type(error).__name__, False, 'Share this report; no exception text is included to protect credentials.')
        status = 1
    finally:
        report.save()
    return status


if __name__ == '__main__':
    sys.exit(main())
