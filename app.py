from flask import Flask, render_template, jsonify, Response, send_from_directory, request
import random
from datetime import datetime
import csv
import io
import socket
import time
import threading
import os
import subprocess
import re
import requests

app = Flask(__name__, static_folder='.', static_url_path='') 

@app.route('/service-worker.js')
def serve_service_worker():
    return send_from_directory('.', 'service-worker.js', mimetype='application/javascript')

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('.', 'manifest.json', mimetype='application/json')

@app.route('/favicon.ico')
def favicon():
    return '', 204

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

LOCAL_IP = get_local_ip()

CSV_FILE = 'sensores_historico.csv'

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Timestamp', 'Temp_C', 'Hum_%', 'Rain_%'])

historicos_graficas = {
    'temp': [], 'humidity': [], 'rain': []
}
historico_times = []

sensor_data = {
    'temp': 0.0, 'humidity': 0.0, 'rain': 0.0,
    'time': '00:00:00',
    'total_registros': 0,
    'modulos_conectados': False
}

historico_csv = []

def modulos_conectados():
    return (20 <= sensor_data['temp'] <= 40 and 
            30 <= sensor_data['humidity'] <= 95 and 
            sensor_data['rain'] >= 0)

def update_data():
    global sensor_data, historicos_graficas, historico_times, historico_csv
    while True:
        try:
            if random.random() < 0.95:
                sensor_data['temp'] = round(random.uniform(20, 35), 1)
                sensor_data['humidity'] = round(random.uniform(40, 90), 1)
                sensor_data['rain'] = round(random.uniform(0, 50), 1)
                sensor_data['modulos_conectados'] = True
            else:
                sensor_data['temp'] = 0.0
                sensor_data['humidity'] = 0.0
                sensor_data['rain'] = 0.0
                sensor_data['modulos_conectados'] = False
            
            now_time = datetime.now().strftime('%H:%M:%S')
            sensor_data['time'] = now_time
            
            if sensor_data['modulos_conectados']:
                historico_times.append(now_time)
                historicos_graficas['temp'].append(sensor_data['temp'])
                historicos_graficas['humidity'].append(sensor_data['humidity'])
                historicos_graficas['rain'].append(sensor_data['rain'])
                
                max_points = 50
                if len(historico_times) > max_points:
                    historico_times.pop(0)
                    for key in historicos_graficas:
                        historicos_graficas[key].pop(0)
                
                registro = [
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    sensor_data['temp'], sensor_data['humidity'], sensor_data['rain']
                ]
                
                historico_csv.append(registro)
                sensor_data['total_registros'] = len(historico_csv)
                
                with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(registro)
                
                if len(historico_csv) > 5000:
                    historico_csv.pop(0)
            
        except Exception as e:
            print(f"Error: {e}")
            
        time.sleep(3)

@app.route('/')
def index():
    return render_template('index_simple.html', 
                         local_ip=LOCAL_IP, 
                         registros=sensor_data['total_registros'],
                         modulos_conectados=sensor_data['modulos_conectados'])

@app.route('/data')
def data():
    return jsonify({
        **sensor_data,
        'temp_history': historicos_graficas['temp'],
        'humidity_history': historicos_graficas['humidity'],
        'rain_history': historicos_graficas['rain'],
        'time_history': historico_times
    })

@app.route('/lora_data', methods=['POST'])
def lora_data():
    """📡 ESP LoRa → Dashboard LIVE"""
    global sensor_data, historicos_graficas, historico_times, historico_csv
    
    try:
        data = request.get_json()
        print(f"📡 ESP → T:{data['temp']:.1f}°C H:{data['humidity']:.1f}% R:{data['rain']:.1f}%")
        
        # Actualiza dashboard INSTANTÁNEO
        sensor_data.update({
            'temp': data.get('temp', 0),
            'humidity': data.get('humidity', 0),
            'rain': data.get('rain', 0),
            'modulos_conectados': data.get('modulos_conectados', True),
            'time': datetime.now().strftime('%H:%M:%S')
        })
        
        # Agrega a gráficos (igual simulación)
        now_time = sensor_data['time']
        historico_times.append(now_time)
        historicos_graficas['temp'].append(sensor_data['temp'])
        historicos_graficas['humidity'].append(sensor_data['humidity']) 
        historicos_graficas['rain'].append(sensor_data['rain'])
        
        # Límite 50 puntos
        if len(historico_times) > 50:
            historico_times.pop(0)
            for key in historicos_graficas:
                historicos_graficas[key].pop(0)
        
        # CSV histórico
        registro = [now_time, sensor_data['temp'], sensor_data['humidity'], sensor_data['rain']]
        historico_csv.append(registro)
        sensor_data['total_registros'] = len(historico_csv)
        
        return jsonify({'status': 'OK', 'time': now_time})
    except Exception as e:
        print(f"❌ ESP Error: {e}")
        return jsonify({'status': 'ERROR'}), 400

@app.route('/csv')
def csv_download():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Timestamp', 'Temp_C', 'Hum_%', 'Rain_%'])
    for row in historico_csv[-1000:]:
        writer.writerow(row)
    output.seek(0)
    filename = f'agromonitor_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/status')
def status():
    size = os.path.getsize(CSV_FILE)/1024/1024 if os.path.exists(CSV_FILE) else 0
    return jsonify({
        'total_registros': sensor_data['total_registros'],
        'modulos_conectados': sensor_data['modulos_conectados'],
        'archivo_tamaño': f"{size:.1f} MB",
        'ultimo_registro': sensor_data['time']
    })

@app.route('/scan_esps')
def scan_esps():
    """🔍 Auto-detect ESPs - CUALQUIER IP"""
    esps = []
    
    print("🔍 === AUTO SCAN ESPs ===")
    
    # 1. ARP scan TODA red local
    try:
        result = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=4)
        ips = re.findall(r'\b(?:192\.168|10\.|172\.1[6-9]|172\.2[0-9]|172\.3[0-1])\.\d{1,3}\b', result.stdout)
        print(f"IPs encontradas: {len(ips)}")
        
        for ip in ips[:20]:  # 20 más rápidos
            print(f"→ Test {ip}")
            try:
                # Test /status JSON
                r = requests.get(f'http://{ip}:80/status', timeout=1.2)
                if r.status_code == 200 and 'temp' in r.text:
                    data = r.json()
                    esps.append({
                        'ip': ip,
                        'name': data.get('device', f'ESP {ip.split(".")[-1]}'),
                        'online': True,
                        'temp': data.get('temp', 0),
                        'humidity': data.get('humidity', 0)
                    })
                    print(f"✅ ESP LIVE: {ip} T{data.get('temp')}")
                    break  # Primer ESP vivo
                
                # Test página config
                r = requests.get(f'http://{ip}:80/', timeout=1.2)
                if r.status_code == 200 and ('ESP' in r.text or 'LoRa' in r.text):
                    esps.append({
                        'ip': ip, 'name': f'ESP Config ({ip})',
                        'online': True, 'temp': 0
                    })
                    print(f"✅ ESP Config: {ip}")
                    break
            except:
                pass
    except Exception as e:
        print(f"ARP error: {e}")
    
    print(f"🔍 RESULTADO: {len(esps)} ESPs")
    return jsonify({'esps': esps})
    
@app.route('/esp_config/<ip>')
def get_esp_config(ip):
    """📥 Config actual del ESP"""
    try:
        response = requests.get(f'http://{ip}:80/status', timeout=2)
        return jsonify(response.json())
    except:
        return jsonify({'error': 'No response'})

@app.route('/esp_status/<ip>')
def esp_status(ip):
    """📊 Status en tiempo real"""
    try:
        response = requests.get(f'http://{ip}:80/status', timeout=2)
        data = response.json()
        data['ip'] = ip
        return jsonify(data)
    except:
        return jsonify({'ip': ip, 'error': 'Offline', 'temp': 0, 'humidity': 0, 'rain': 0})

@app.route('/configurar_esp/<ip>', methods=['POST'])
def configurar_esp(ip):
    """🚀 Enviar config al ESP"""
    try:
        config = request.get_json()
        response = requests.post(f'http://{ip}:80/save', 
                               json=config, timeout=5)
        
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'ESP configurado y reiniciando...'})
        else:
            return jsonify({'success': False, 'error': f'HTTP {response.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/csv_view.html')
def csv_view():
    try:                                   
        return render_template('csv_view.html') 
    except:                                 
        return "Crear templates/csv_view.html"
        
@app.route('/index_simple.html')
def index_simple_direct():
    return render_template('index_simple.html')

@app.route('/data_full')
def data_full():
    return jsonify({
        'csv_history': historico_csv[-1000:],
        'total_registros': sensor_data['total_registros']
    })

@app.route('/public/<path:filename>')
def public_files(filename):
    """📁 Servir archivos de public/"""
    return send_from_directory('public', filename)

@app.route('/esp-proxy')
def esp_proxy():
    """🌐 Proxy CORS para ESP (cualquier IP)"""
    target = request.args.get('target')
    if not target or not re.match(r'^http://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', target):
        return jsonify({'error': 'URL inválida'}), 400
    
    try:
        resp = requests.request(
            method=request.method,
            url=target,
            params={k: v[0] for k, v in request.args.items() if k != 'target'},
            data=request.get_data(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=5
        )
        return Response(resp.content, resp.status_code, 
                       [(k, v) for k, v in resp.headers.items()])
    except Exception as e:
        return jsonify({'error': f'ESP offline: {str(e)}'}), 503

if __name__ == '__main__':
    threading.Thread(target=update_data, daemon=True).start()
    time.sleep(2)
    print("\n🌱 === AGROMONITOR v5.2 - SIN LoRa ===")
    print(f"📱 http://{LOCAL_IP}:8080")
    print("✅ Solo Temp/Hum/Rain + Estado módulos")
    app.run(host='0.0.0.0', port=8080, debug=False)
