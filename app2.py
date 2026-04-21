from flask import Flask, render_template, jsonify, Response
import random
from datetime import datetime
import csv
import io
import socket
import time
import threading
import os

app = Flask(__name__)

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
        writer.writerow(['Timestamp', 'Temp_C', 'Hum_%', 'Rain_%', 'Status'])

historicos_graficas = {
    'temp': [], 'humidity': [], 'rain': []
}
historico_times = []

sensor_data = {
    'temp': 0.0, 'humidity': 0.0, 'rain': 0.0,
    'status': '⏳ ESPERANDO DATOS...',
    'time': datetime.now().strftime('%H:%M:%S'),
    'total_registros': 0,
    'sensores_conectados': False
}

historico_csv = []

def update_data():
    global sensor_data, historicos_graficas, historico_times, historico_csv
    while True:
        try:
            # 🎯 MODO DEMO: datos en 0 hasta conectar sensores reales
            # Cuando conectes sensores reales, reemplaza esta sección:
            
            if sensor_data['sensores_conectados']:  # ✅ Solo genera datos reales cuando estén conectados
                sensor_data['temp'] = round(random.uniform(20, 30), 1)
                sensor_data['humidity'] = round(random.uniform(50, 85), 1)
                sensor_data['rain'] = round(random.uniform(0, 50), 1)
                sensor_data['status'] = '🟢 CONECTADO'
            else:
                sensor_data['temp'] = 0.0
                sensor_data['humidity'] = 0.0
                sensor_data['rain'] = 0.0
                sensor_data['status'] = '⏳ ESPERANDO SENSORE(S)...'
            
            now_time = datetime.now().strftime('%H:%M:%S')
            sensor_data['time'] = now_time
            
            # 📈 GRÁFICAS (solo si hay datos reales)
            if sensor_data['sensores_conectados']:
                historico_times.append(now_time)
                historicos_graficas['temp'].append(sensor_data['temp'])
                historicos_graficas['humidity'].append(sensor_data['humidity'])
                historicos_graficas['rain'].append(sensor_data['rain'])
                
                max_points = 50
                if len(historico_times) > max_points:
                    historico_times.pop(0)
                    for key in historicos_graficas:
                        historicos_graficas[key].pop(0)
            
            # 💾 CSV (solo si hay datos reales)
            if sensor_data['sensores_conectados']:
                registro = [
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    sensor_data['temp'], sensor_data['humidity'], sensor_data['rain'],
                    sensor_data['status']
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
                         registros=sensor_data['total_registros'])

@app.route('/data')
def data():
    return jsonify({
        **sensor_data,
        'temp_history': historicos_graficas['temp'],
        'humidity_history': historicos_graficas['humidity'],
        'rain_history': historicos_graficas['rain'],
        'time_history': historico_times
    })

@app.route('/csv')
def csv_download():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Timestamp', 'Temp_C', 'Hum_%', 'Rain_%', 'Status'])
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
        'archivo_tamaño': f"{size:.1f} MB",
        'ultimo_registro': sensor_data['time'],
        'sensores_conectados': sensor_data['sensores_conectados']
    })

# 🔧 ENDPOINT PARA SIMULAR CONEXIÓN DE SENSores (para pruebas)
@app.route('/connect_sensors/<int:connected>')
def connect_sensors(connected):
    global sensor_data
    sensor_data['sensores_conectados'] = bool(connected)
    status = '🟢 CONECTADO' if connected else '⏳ ESPERANDO SENSORE(S)...'
    return jsonify({'status': status, 'sensores_conectados': bool(connected)})

if __name__ == '__main__':
    threading.Thread(target=update_data, daemon=True).start()
    time.sleep(2)
    print("\n🌱 === AGROMONITOR v6.0 - SIN LoRa ===")
    print(f"📱 http://{LOCAL_IP}:8080")
    print("✅ 3 sensores | Datos en 0 hasta conectar | Fondo BLANCO")
    print("🔧 Para pruebas: http://IP:8080/connect_sensors/1")
    app.run(host='0.0.0.0', port=8080, debug=False)
