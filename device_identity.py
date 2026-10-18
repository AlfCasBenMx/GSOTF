"""Public display name checks; never sends service keys or raw hardware serials."""
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request

DEFAULT_NAME_CHECK = 'https://liper-health-monitor.loftygrebe10.chatgpt.site/api/name-availability'


class NameTaken(ValueError):
    pass


class NameCheckUnavailable(RuntimeError):
    pass


def clean_label(value):
    label = ' '.join(value.split())
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{2,39}', label):
        raise ValueError('Usa 3 a 40 caracteres: letras sin acentos, numeros, espacios, guion o guion bajo.')
    return label


def check_label(label, health_url='', serial=None):
    label = clean_label(label)
    endpoint = DEFAULT_NAME_CHECK
    if health_url:
        parsed = urllib.parse.urlsplit(health_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise NameCheckUnavailable('No se pudo consultar el monitor.')
        endpoint = urllib.parse.urlunsplit(('https', parsed.netloc, '/api/name-availability', '', ''))
    if serial is None:
        serial = os.environ.get('GDF_SERIAL', '').strip()
        path = Path('/sys/firmware/devicetree/base/serial-number')
        if not serial and path.exists():
            serial = path.read_text().strip('\0\r\n ')[:16]
    query = {'name': label}
    if serial:
        query['device'] = hashlib.sha256(serial.encode('utf-8')).hexdigest()
    try:
        request = urllib.request.Request(endpoint + '?' + urllib.parse.urlencode(query), headers={'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read(8192))
        if type(data.get('available')) is not bool:
            raise ValueError('Invalid response')
    except (OSError, ValueError):
        raise NameCheckUnavailable('No se pudo validar el nombre en el monitor.')
    if not data['available']:
        raise NameTaken('Ese nombre ya pertenece a otra Raspberry en el monitor.')
    return {'checked': True, 'same_device': bool(data.get('same_device')), 'reserved': False}


def runtime_values(path):
    values = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    try:
                        value = json.loads(value)
                    except ValueError:
                        pass
                values[key.strip()] = value
    return values


def save_label(path, label):
    path = Path(path)
    lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    lines = [line for line in lines if not line.strip().startswith('GDF_HEALTH_LABEL=')]
    lines.append('GDF_HEALTH_LABEL=' + json.dumps(clean_label(label)))
    temporary = path.with_suffix('.label.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        os.chmod(str(temporary), 0o600)
        stream.write('\n'.join(lines) + '\n')
    if path.exists() and hasattr(os, 'chown'):
        owner = path.stat()
        os.chown(str(temporary), owner.st_uid, owner.st_gid)
    os.replace(str(temporary), str(path))
