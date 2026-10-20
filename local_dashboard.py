"""Loopback-only, bounded in-memory preview. Never opens a camera or calls OCR."""
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4


PAGE = '''<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LIPER · Cámara y lecturas</title><style>
body{margin:0;background:#101923;color:#edf4fa;font:16px system-ui;padding:24px}
header{display:flex;justify-content:space-between;gap:20px;align-items:center}
h1{font-size:26px}small,#status{color:#a9c3d7}main{display:grid;grid-template-columns:2fr 1fr;gap:24px}
#live{width:100%;min-height:200px;object-fit:contain;background:#080e15;border-radius:14px}
article{display:flex;gap:14px;background:#1c2a38;padding:12px;border-radius:12px;margin-bottom:10px}
article img{width:130px;height:75px;object-fit:contain;background:#080e15}strong{font-size:23px}
p{line-height:1.5}.empty{padding:20px;background:#1c2a38;border-radius:12px}
@media(max-width:850px){main{grid-template-columns:1fr}body{padding:14px}}
</style><header><h1>LIPER · Cámara y lecturas</h1><span id="status">Esperando cámara…</span></header>
<main><section><img id="live" alt="Esperando el primer fotograma"><p><small>Vista reducida de la captura del lector. Su frecuencia depende del procesamiento de la Raspberry.</small></p></section>
<section><h2>Últimas 5 placas distintas</h2><div id="plates" class="empty">Aún no hay lecturas en esta sesión.</div>
<p><small>Texto devuelto por OCR; esta vista no confirma entrega a Genyus. El historial de este panel se reinicia al detener el lector.</small></p></section></main>
<script>
let lastFrame=0,lastPlates='';
async function update(){try{
 const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)throw Error();const s=await r.json();
 const age=s.frame_at?(Date.now()/1000-s.frame_at):null;
 document.getElementById('status').textContent=age===null?'Esperando cámara…':age>10?'Sin fotograma reciente · '+Math.floor(age)+' s':'Cámara activa · hace '+Math.max(0,Math.floor(age))+' s';
 if(s.frame_at&&s.frame_at!==lastFrame){document.getElementById('live').alt='Camara del lector';document.getElementById('live').src='/frame.jpg?v='+s.frame_at;lastFrame=s.frame_at;}
 const key=JSON.stringify(s.plates);if(key!==lastPlates){const box=document.getElementById('plates');box.replaceChildren();box.className=s.plates.length?'':'empty';
 if(!s.plates.length)box.textContent='Aún no hay lecturas en esta sesión.';
 for(const p of s.plates){const row=document.createElement('article'),img=document.createElement('img'),info=document.createElement('div'),text=document.createElement('strong'),when=document.createElement('div');
 img.src='/crop/'+p.id+'.jpg';img.alt='Recorte enviado al OCR';text.textContent=p.plate;when.textContent=new Date(p.read_at*1000).toLocaleString();info.append(text,when);row.append(img,info);box.append(row);}lastPlates=key;}
 }catch(e){document.getElementById('status').textContent='Lector desconectado; intentando reconectar…';}finally{setTimeout(update,1000);}}
update();</script></html>'''.encode('utf-8')


class DashboardState:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.frame_at = 0
        self.plates = []
        self.viewer_at = 0

    def wants_preview(self):
        with self.lock:
            return time.monotonic() - self.viewer_at < 15

    def set_frame(self, jpeg):
        if len(jpeg) > 512 * 1024:
            return
        with self.lock:
            self.frame, self.frame_at = jpeg, time.time()

    def add_plate(self, plate, jpeg):
        plate = re.sub('[^A-Z0-9]', '', plate.upper())
        if not 4 < len(plate) < 8 or not jpeg or len(jpeg) > 512 * 1024:
            return
        with self.lock:
            self.plates = [p for p in self.plates if p['plate'] != plate]
            self.plates.insert(0, dict(id=uuid4().hex, plate=plate,
                                       read_at=time.time(), jpeg=jpeg))
            del self.plates[5:]

    def snapshot(self):
        with self.lock:
            self.viewer_at = time.monotonic()
            return dict(frame_at=self.frame_at,
                        plates=[{k: v for k, v in p.items() if k != 'jpeg'} for p in self.plates])

    def image(self, path):
        with self.lock:
            if path == '/frame.jpg':
                return self.frame
            for plate in self.plates:
                if path == '/crop/' + plate['id'] + '.jpg':
                    return plate['jpeg']
        return None


STATE = DashboardState()
ACTIVE = threading.Event()


def record_reading(plates, crop_bytes):
    if not ACTIVE.is_set() or not plates:
        return
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(crop_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return
    scale = min(1, 240 / image.shape[1], 160 / image.shape[0])
    if scale < 1:
        image = cv2.resize(image, (max(1, int(image.shape[1]*scale)), max(1, int(image.shape[0]*scale))))
    ok, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if ok:
        data = jpeg.tobytes()
        for plate in plates:
            STATE.add_plate(plate, data)


def start(port=8765, state=None):
    state = state if state is not None else STATE

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Reject cross-origin DNS rebinding access to local plate data.
            if self.headers.get('Host') not in ('127.0.0.1:%d' % self.server.server_port,
                                                 'localhost:%d' % self.server.server_port):
                self.send_error(403)
                return
            path = self.path.split('?', 1)[0]
            if path == '/':
                data, kind = PAGE, 'text/html; charset=utf-8'
            elif path == '/api/state':
                data, kind = json.dumps(state.snapshot()).encode(), 'application/json'
            else:
                data, kind = state.image(path), 'image/jpeg'
            if data is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    ACTIVE.set()
    return server
