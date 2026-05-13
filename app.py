"""
AgroMonitor v6.0 — Corregido para Render (cloud)
Fixes:
  - Sin simulación falsa en producción
  - Estado compartido thread-safe con Lock
  - 1 solo worker gunicorn (estado en memoria)
  - Sin escritura CSV en disco (Render efímero)
  - Sin scan ARP (no funciona en cloud)
  - Sin LOCAL_IP inútil
  - global declarado correctamente
  - Keepalive endpoint para evitar sleep en Render free
"""

from flask import Flask, render_template, jsonify, Response, send_from_directory, request
from flask_cors import CORS
import json
import re
import io
import csv
import os
import time
import socket
import threading
import requests
from datetime import datetime

# ─── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})

# ─── Estado global thread-safe ─────────────────────────────────────────────────
_lock = threading.Lock()

sensor_data = {
    'temp': 0.0,
    'humidity': 0.0,
    'rain': 0.0,
    'rssi': 0,
    'time': '--:--:--',
    'total_registros': 0,
    'modulos_conectados': False,
    'ultimo_dato': None,          # timestamp del último dato recibido del ESP
}

historicos_graficas = {'temp': [], 'humidity': [], 'rain': []}
historico_times     = []
historico_csv       = []          # RAM (máx 5000 registros — Render no tiene disco persistente)

MAX_POINTS  = 50
MAX_CSV_RAM = 5000

# ─── Helpers ───────────────────────────────────────────────────────────────────

def _push_historico(temp, humidity, rain, now_time):
    """Agrega punto a las gráficas (dentro de _lock)."""
    historico_times.append(now_time)
    historicos_graficas['temp'].append(temp)
    historicos_graficas['humidity'].append(humidity)
    historicos_graficas['rain'].append(rain)
    if len(historico_times) > MAX_POINTS:
        historico_times.pop(0)
        for k in historicos_graficas:
            historicos_graficas[k].pop(0)

    registro = [
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        temp, humidity, rain
    ]
    historico_csv.append(registro)
    if len(historico_csv) > MAX_CSV_RAM:
        historico_csv.pop(0)
    sensor_data['total_registros'] = len(historico_csv)


def _esp_timeout_watchdog():
    """
    Hilo liviano: marca módulos como desconectados si no llegan datos
    del ESP en más de 30 segundos. Evita mostrar datos viejos como 'vivos'.
    """
    while True:
        time.sleep(10)
        with _lock:
            ultimo = sensor_data.get('ultimo_dato')
            if ultimo is not None:
                elapsed = (datetime.now() - ultimo).total_seconds()
                if elapsed > 30:
                    sensor_data['modulos_conectados'] = False


threading.Thread(target=_esp_timeout_watchdog, daemon=True).start()


# ─── Rutas estáticas ───────────────────────────────────────────────────────────

@app.route('/service-worker.js')
def serve_service_worker():
    return send_from_directory('.', 'service-worker.js', mimetype='application/javascript')

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('.', 'manifest.json', mimetype='application/json')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/public/<path:filename>')
def public_files(filename):
    return send_from_directory('public', filename)


# ─── Páginas ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    with _lock:
        registros  = sensor_data['total_registros']
        conectados = sensor_data['modulos_conectados']
    return render_template('index_simple.html',
                           registros=registros,
                           modulos_conectados=conectados)

@app.route('/csv_view.html')
def csv_view():
    return render_template('csv_view.html')

@app.route('/index_simple.html')
def index_simple_direct():
    return render_template('index_simple.html')


# ─── API: recibir datos del ESP ────────────────────────────────────────────────

def _procesar_dato_esp(temp, humidity, rain, rssi=0):
    """Actualiza el estado global con un dato recibido del ESP."""
    now_time = datetime.now().strftime('%H:%M:%S')
    with _lock:
        sensor_data.update({
            'temp': temp,
            'humidity': humidity,
            'rain': rain,
            'rssi': rssi,
            'modulos_conectados': True,
            'time': now_time,
            'ultimo_dato': datetime.now(),
        })
        _push_historico(temp, humidity, rain, now_time)


@app.route('/api/datos', methods=['POST'])
def api_datos():
    """📡 ESP WiFi → Dashboard LIVE"""
    try:
        raw = request.get_data().decode(errors='ignore')
        print(f"🔍 ESP RAW: {raw[:200]}")

        if request.is_json:
            data = request.get_json(force=True) or {}
        else:
            data = request.form.to_dict()

        temp     = float(data.get('temp',     data.get('t', 0)))
        humidity = float(data.get('humidity', data.get('h', 0)))
        rain     = float(data.get('rain',     data.get('r', 0)))
        rssi     = int(  data.get('rssi', -100))

        print(f"✅ ESP → T:{temp}°C H:{humidity}% R:{rain}% RSSI:{rssi}")
        _procesar_dato_esp(temp, humidity, rain, rssi)
        return jsonify({'status': 'OK'}), 200

    except Exception as e:
        print(f"❌ ESP Error: {e}")
        return jsonify({'status': 'ERROR', 'error': str(e)}), 400


@app.route('/api/datos', methods=['GET'])
def api_datos_get():
    """🔍 Test endpoint — el ESP puede hacer GET para verificar conectividad."""
    return jsonify({
        'status': 'OK',
        'message': 'AgroMonitor listo para recibir datos del ESP',
        'timestamp': datetime.now().isoformat(),
        'endpoint_post': '/api/datos',
        'fields': ['temp (o t)', 'humidity (o h)', 'rain (o r)', 'rssi'],
    })


@app.route('/lora_data', methods=['POST'])
def lora_data():
    """📡 ESP LoRa → Dashboard LIVE"""
    try:
        data = request.get_json(force=True) or {}
        print(f"📡 LoRa → T:{data.get('temp',0):.1f}°C H:{data.get('humidity',0):.1f}% R:{data.get('rain',0):.1f}%")
        _procesar_dato_esp(
            temp=float(data.get('temp', 0)),
            humidity=float(data.get('humidity', 0)),
            rain=float(data.get('rain', 0)),
            rssi=int(data.get('rssi', 0)),
        )
        return jsonify({'status': 'OK', 'time': sensor_data['time']})
    except Exception as e:
        print(f"❌ LoRa Error: {e}")
        return jsonify({'status': 'ERROR', 'error': str(e)}), 400


# ─── API: leer datos ───────────────────────────────────────────────────────────

@app.route('/data')
def data():
    with _lock:
        return jsonify({
            **sensor_data,
            'ultimo_dato': sensor_data['ultimo_dato'].isoformat() if sensor_data['ultimo_dato'] else None,
            'temp_history':     list(historicos_graficas['temp']),
            'humidity_history': list(historicos_graficas['humidity']),
            'rain_history':     list(historicos_graficas['rain']),
            'time_history':     list(historico_times),
        })


@app.route('/api/status')
def api_status():
    """📊 Status completo para el dashboard."""
    with _lock:
        return jsonify({
            'temp':              sensor_data['temp'],
            'humidity':          sensor_data['humidity'],
            'rain':              sensor_data['rain'],
            'rssi':              sensor_data.get('rssi', 0),
            'timestamp':         sensor_data['time'],
            'device':            'ESP_AgroScan',
            'modulos_conectados': sensor_data['modulos_conectados'],
        })


@app.route('/status')
def status():
    with _lock:
        return jsonify({
            'total_registros':   sensor_data['total_registros'],
            'modulos_conectados': sensor_data['modulos_conectados'],
            'archivo_tamaño':    f"{len(historico_csv) * 50 / 1024:.1f} KB (RAM)",
            'ultimo_registro':   sensor_data['time'],
        })


@app.route('/data_full')
def data_full():
    with _lock:
        return jsonify({
            'csv_history':    list(historico_csv[-1000:]),
            'total_registros': sensor_data['total_registros'],
        })


# ─── CSV download ──────────────────────────────────────────────────────────────

@app.route('/csv')
def csv_download():
    with _lock:
        rows = list(historico_csv[-1000:])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Timestamp', 'Temp_C', 'Hum_%', 'Rain_%'])
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    filename = f'agromonitor_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# ─── ESP Proxy (CORS bridge) ───────────────────────────────────────────────────

# IPs privadas permitidas (RFC 1918)
_PRIVATE_IP_RE = re.compile(
    r'^http://'
    r'(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}'
    r'|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}'
    r'|192\.168\.\d{1,3}\.\d{1,3})'
    r'(?::\d{1,5})?(?:/.*)?$'
)

@app.route('/esp-proxy', methods=['GET', 'POST'])
def esp_proxy():
    """🌐 Proxy CORS para ESP — solo IPs privadas RFC 1918."""
    target = request.args.get('target', '')

    if not _PRIVATE_IP_RE.match(target):
        return jsonify({'error': 'URL inválida — solo IPs privadas permitidas', 'target': target}), 400

    print(f"🔍 ESP Proxy → {target} ({request.method})")
    try:
        session = requests.Session()
        if request.method == 'POST':
            form_data = request.form.to_dict() if request.form else {}
            resp = session.post(target, data=form_data, timeout=8,
                                headers={'Content-Type': 'application/x-www-form-urlencoded'})
        else:
            resp = session.get(target, timeout=8)

        content = resp.content.decode('utf-8', errors='ignore')
        try:
            return jsonify(json.loads(content))
        except Exception:
            return Response(content, status=200, mimetype='text/plain')

    except requests.exceptions.Timeout:
        return jsonify({'error': 'ESP timeout — no responde en 8s'})
    except Exception as e:
        print(f"❌ Proxy error: {e}")
        return jsonify({
            'error': 'ESP offline o inaccesible desde la nube',
            'target': target,
            'tip': 'El proxy solo funciona en red local. Usa /api/datos para enviar datos desde el ESP directamente a Render.',
        })


# ─── ESP config (local only) ──────────────────────────────────────────────────

@app.route('/esp_status/<ip>')
def esp_status(ip):
    """📊 Status del ESP — solo funciona en red local."""
    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
        return jsonify({'error': 'IP inválida'}), 400
    try:
        response = requests.get(f'http://{ip}:80/status', timeout=3)
        data = response.json()
        data['ip'] = ip
        return jsonify(data)
    except Exception:
        return jsonify({'ip': ip, 'error': 'Offline', 'temp': 0, 'humidity': 0, 'rain': 0})


@app.route('/esp_config/<ip>')
def get_esp_config(ip):
    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
        return jsonify({'error': 'IP inválida'}), 400
    try:
        response = requests.get(f'http://{ip}:80/status', timeout=3)
        return jsonify(response.json())
    except Exception:
        return jsonify({'error': 'No response'})


@app.route('/configurar_esp/<ip>', methods=['POST'])
def configurar_esp(ip):
    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
        return jsonify({'success': False, 'error': 'IP inválida'}), 400
    try:
        config = request.get_json()
        response = requests.post(f'http://{ip}:80/save', json=config, timeout=5)
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'ESP configurado y reiniciando...'})
        return jsonify({'success': False, 'error': f'HTTP {response.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/scan_esps')
def scan_esps():
    """
    ⚠️ scan_esps no funciona en Render (cloud sin red local).
    Retorna mensaje claro en lugar de fallar silenciosamente.
    """
    return jsonify({
        'esps': [],
        'mensaje': 'El escaneo ARP no está disponible en producción (cloud). '
                   'Configura el ESP para enviar datos directamente a '
                   'https://agromonitor-d2wa.onrender.com/api/datos',
        'endpoint_esp': '/api/datos',
        'metodo': 'POST',
        'campos': {'temp': 25.3, 'humidity': 65.0, 'rain': 0.0, 'rssi': -70},
    })


# ─── Keepalive (evita sleep en Render free) ────────────────────────────────────

@app.route('/ping')
def ping():
    """Endpoint liviano para keepalive externo (ej: UptimeRobot cada 5 min)."""
    return jsonify({'pong': True, 'ts': datetime.now().isoformat()})


# ─── Arranque local ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Detectar IP local solo para desarrollo
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = '127.0.0.1'

    print("\n🌱 === AGROMONITOR v6.0 — LOCAL ===")
    print(f"📱 http://{local_ip}:8080")
    print(f"🔗 POST datos ESP → http://{local_ip}:8080/api/datos")
    print("✅ Sin simulación falsa — solo datos reales del ESP\n")
    app.run(host='0.0.0.0', port=8080, debug=False)
