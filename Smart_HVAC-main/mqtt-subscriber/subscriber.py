import paho.mqtt.client as mqtt
import json
import psycopg2
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlparse

# Config
MQTT_BROKER = os.getenv('MQTT_BROKER', 'mosquitto')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
DB_HOST = os.getenv('DB_HOST', 'timescaledb')
DB_NAME = os.getenv('DB_NAME', 'iotdb')
DB_USER = os.getenv('DB_USER', 'admin')
DB_PASS = os.getenv('DB_PASSWORD', 'admin123')
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', '5000'))
CONTROL_TOPIC = os.getenv('CONTROL_TOPIC', 'remote-control')

# ====================== DATABASE ======================
def get_db_connection():
    last_error = None
    for attempt in range(1, 11):
        try:
            return psycopg2.connect(
                host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS
            )
        except psycopg2.OperationalError as error:
            last_error = error
            print(f"⏳ Waiting for database... attempt {attempt}/10")
            time.sleep(2)

    raise last_error

conn = get_db_connection()
cur = conn.cursor()

# Tạo bảng + hypertable
cur.execute("""
CREATE TABLE IF NOT EXISTS sensor_data (
    time TIMESTAMPTZ NOT NULL,
    device_id TEXT,
    temperature FLOAT,
    outdoor_temperature FLOAT,
    humidity FLOAT,
    co2 INT,
    dust FLOAT,
    PRIMARY KEY (time, device_id)
);

CREATE TABLE IF NOT EXISTS remote_control_state (
    time TIMESTAMPTZ NOT NULL,
    device_id TEXT NOT NULL,
    power BOOLEAN NOT NULL,
    temp FLOAT NOT NULL,
    operation_mode TEXT NOT NULL,
    fan_power TEXT NOT NULL,
    client_id TEXT,
    requested_at TIMESTAMPTZ,
    PRIMARY KEY (time, device_id)
);

ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS outdoor_temperature FLOAT;
ALTER TABLE remote_control_state ADD COLUMN IF NOT EXISTS client_id TEXT;
ALTER TABLE remote_control_state ADD COLUMN IF NOT EXISTS requested_at TIMESTAMPTZ;
ALTER TABLE remote_control_state ADD COLUMN IF NOT EXISTS co2_max FLOAT;
ALTER TABLE remote_control_state ADD COLUMN IF NOT EXISTS humidity_max FLOAT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS power_w FLOAT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS energy_kwh FLOAT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS power_base_w FLOAT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS energy_base_kwh FLOAT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS power_ac_w FLOAT;
ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS power_fan_w FLOAT;
SELECT create_hypertable('sensor_data', 'time', if_not_exists => TRUE);
SELECT create_hypertable('remote_control_state', 'time', if_not_exists => TRUE);
""")
conn.commit()

def is_outdoor_device(device_id):
    normalized = (device_id or '').lower()
    return any(token in normalized for token in ['outdoor', 'outside', 'ngoai', 'ngoài'])

def to_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None

def to_int(value):
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None

def get_outdoor_temperature(payload):
    for key in ['outdoor_temperature', 'outdoorTemp', 'outside_temperature', 'outsideTemp']:
        value = to_float(payload.get(key))
        if value is not None:
            return value
    return None

def calculate_simulated_power(payload, latest_control):
    # Baseload / Standby power for sensor/electronics
    standby_power = 5.0
    ac_power = 0.0
    fan_power = 0.0
    
    current_temp = to_float(payload.get('temperature'))
    co2 = to_int(payload.get('co2'))
    humidity = to_float(payload.get('humidity'))
    
    # 1. AC Power for AI-optimized state
    if latest_control:
        device_power_on = latest_control.get('power', False)
        target_temp = latest_control.get('temp', 25.0)
        op_mode = latest_control.get('operationMode', 'auto')
        fan_speed = latest_control.get('fanPower', 'auto')
        
        if device_power_on:
            if op_mode == 'off':
                ac_power = 0.0
            elif op_mode == 'fan':
                ac_power = 12.0  # Only indoor fan circulating air
            else:
                # determine cooling/heating
                is_cooling = True
                if op_mode == 'heat':
                    is_cooling = False
                elif op_mode == 'auto' and current_temp is not None:
                    is_cooling = current_temp > target_temp
                    
                if current_temp is not None:
                    if is_cooling:
                        delta_t = current_temp - target_temp
                        if delta_t <= 0:
                            ac_power = 150.0  # Inverter compressor at lowest frequency
                        else:
                            ac_power = 250.0 + 400.0 * delta_t
                            if ac_power > 1400.0:
                                ac_power = 1400.0
                    else:  # Heating
                        delta_t = target_temp - current_temp
                        if delta_t <= 0:
                            ac_power = 100.0
                        else:
                            ac_power = 200.0 + 350.0 * delta_t
                            if ac_power > 1200.0:
                                ac_power = 1200.0
                else:
                    ac_power = 300.0  # Default moderate cooling load
                    
        # 2. Fan Power for AI-optimized state
        fan_running = False
        if fan_speed in ['on', 'high', 'medium', 'low']:
            fan_running = True
        elif fan_speed == 'auto':
            co2_max = latest_control.get('co2Max', 800.0)
            humidity_max = latest_control.get('humidityMax', 60.0)
            if co2 is not None and co2 > co2_max:
                fan_running = True
            if humidity is not None and humidity > humidity_max:
                fan_running = True
                
        if fan_running:
            fan_power = 45.0  # Fan power draw
            
    total_power_w = standby_power + ac_power + fan_power
    
    # 3. Baseline Power (Traditional setup: constant Cool mode @ 24C, fan always ON)
    ac_base_power = 0.0
    if current_temp is not None:
        delta_t_base = current_temp - 24.0
        if delta_t_base <= 0:
            ac_base_power = 150.0
        else:
            ac_base_power = 250.0 + 400.0 * delta_t_base
            if ac_base_power > 1400.0:
                ac_base_power = 1400.0
    else:
        ac_base_power = 350.0
        
    fan_base_power = 45.0  # Traditional fan is always ON for ventilation safety
    total_base_power_w = standby_power + ac_base_power + fan_base_power
    
    return {
        'power_w': total_power_w,
        'power_ac_w': ac_power,
        'power_fan_w': fan_power,
        'power_base_w': total_base_power_w
    }

# ====================== AI ZONE MANAGER ======================
class ZoneManager:
    def __init__(self):
        self.client = None
        self.current_policy = "working_hours"  # "working_hours", "night_eco", "eco_standby", "manual"
        self.override_until = 0  # Timestamp khi manual override kích hoạt
        self.last_applied_state = {}
        self.last_recommendation = "Hệ thống hoạt động tối ưu."

    def get_scheduled_policy(self):
        import datetime
        now = datetime.datetime.now()
        hour = now.hour
        
        # 8h sáng - 17h chiều: Giờ làm việc (Working Hours)
        if 8 <= hour < 17:
            return "working_hours"
        # 10h đêm - 6h sáng: Tiết kiệm ban đêm (Night Eco)
        elif hour >= 22 or hour < 6:
            return "night_eco"
        # Các giờ khác: Chế độ chờ tiết kiệm (Eco Standby)
        else:
            return "eco_standby"

    def set_client(self, client):
        self.client = client

    def evaluate_and_control(self, device_id, temperature, co2, humidity, outdoor_temp):
        """
        Thuật toán điều khiển phối hợp dựa trên XGB-DQN (Free cooling) và Chính sách Zone.
        """
        import time
        
        if time.time() < self.override_until:
            self.current_policy = "manual"
            self.last_recommendation = f"Chế độ chỉnh tay đang hoạt động. Còn {int(self.override_until - time.time())} giây."
            return
 
        policy = self.get_scheduled_policy()
        self.current_policy = policy
        
        power = True
        target_temp = 25.0
        op_mode = "auto"
        fan_power = "auto"
        
        # Ngưỡng CO2 và Độ ẩm tối ưu tự động bởi AI
        co2_max = 800.0
        humidity_max = 60.0
        reason = "Đang áp dụng chính sách thời gian mặc định."
 
        # Logic XGB-DQN (Free Cooling):
        if outdoor_temp is not None and outdoor_temp < temperature - 1.5 and policy != "eco_standby":
            target_temp = 28.0  
            op_mode = "fan"     
            fan_power = "high"  
            co2_max = 600.0      # Hạ thấp ngưỡng CO2 để tối đa lấy gió trời sạch
            humidity_max = 55.0  # Hạ thấp độ ẩm để tận dụng gió mát khô ráo bên ngoài
            reason = f"AI phát hiện trời mát ({outdoor_temp:.1f}°C) hơn trong phòng ({temperature:.1f}°C). Khuyến nghị MỞ CỬA SỔ và chạy quạt thông gió để làm mát tự nhiên!"
        else:
            if policy == "working_hours":
                target_temp = 24.5  
                op_mode = "auto"
                fan_power = "auto"
                co2_max = 700.0      # Hạ thấp ngưỡng CO2 giúp đầu óc tỉnh táo làm việc hiệu quả
                humidity_max = 60.0  # Độ ẩm dễ chịu tối ưu
                reason = "Chính sách Giờ làm việc (08:00 - 17:00). Duy trì độ mát tối ưu."
            elif policy == "night_eco":
                target_temp = 26.5  
                op_mode = "auto"
                fan_power = "low"   
                co2_max = 950.0      # Nâng cao ngưỡng CO2 để tránh quạt đóng ngắt gây ồn khi ngủ
                humidity_max = 65.0  # Tăng nhẹ độ ẩm
                reason = "Chính sách Ngủ đêm ECO. Tăng nhẹ nhiệt độ và giảm ồn quạt."
            elif policy == "eco_standby":
                power = False
                target_temp = 28.0
                op_mode = "off"
                fan_power = "off"
                co2_max = 1200.0     # Tăng cao ngưỡng CO2 do phòng không có người để tiết kiệm điện
                humidity_max = 75.0
                reason = "Ngoài giờ làm việc. Đưa Zone về chế độ chờ Standby tiết kiệm điện."
 
        self.last_recommendation = reason
 
        new_state = {
            "power": power,
            "temp": target_temp,
            "operationMode": op_mode,
            "fanPower": fan_power,
            "co2Max": co2_max,
            "humidityMax": humidity_max
        }
 
        if self.last_applied_state.get(device_id) != new_state:
            self.last_applied_state[device_id] = new_state
            
            command = {
                "device_id": device_id,
                "power": power,
                "temp": target_temp,
                "operationMode": op_mode,
                "fanPower": fan_power,
                "co2Max": co2_max,
                "humidityMax": humidity_max,
                "clientId": "ai-zone-manager",
                "requestedAt": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            }
            
            if self.client:
                try:
                    self.client.publish(CONTROL_TOPIC, json.dumps(command), qos=1)
                    save_remote_control_state(command)
                    print(f"🤖 AI Zone Manager [{policy}]: Đã đẩy Setpoint & Ngưỡng tối ưu xuống ESP32 → Temp: {target_temp}°C | CO2: {co2_max} ppm | lý do: {reason}")
                except Exception as e:
                    print(f"❌ Zone Manager publish error: {e}")

# Khởi tạo đối tượng toàn cục
zone_manager = ZoneManager()

def fetch_telemetry():
    with get_db_connection() as api_conn:
        with api_conn.cursor() as api_cur:
            api_cur.execute("""
                SELECT time, device_id, temperature, outdoor_temperature, humidity, co2, dust, power_w, energy_kwh, power_base_w, energy_base_kwh, power_ac_w, power_fan_w
                FROM sensor_data
                ORDER BY time DESC
                LIMIT 200
            """)
            rows = api_cur.fetchall()

            api_cur.execute("""
                SELECT time, device_id, power, temp, operation_mode, fan_power, client_id, requested_at, co2_max, humidity_max
                FROM remote_control_state
                ORDER BY time DESC
                LIMIT 1
            """)
            control_row = api_cur.fetchone()

    latest_primary = None
    latest_outdoor = None
    for row in rows:
        point = {
            'time': row[0].isoformat(),
            'device_id': row[1],
            'temperature': row[2],
            'outdoor_temperature': row[3],
            'humidity': row[4],
            'co2': row[5],
            'dust': row[6],
            'power': row[7] if len(row) > 7 and row[7] is not None else 0.0,
            'energy': row[8] if len(row) > 8 and row[8] is not None else 0.0,
            'power_base': row[9] if len(row) > 9 and row[9] is not None else 0.0,
            'energy_base': row[10] if len(row) > 10 and row[10] is not None else 0.0,
            'power_ac': row[11] if len(row) > 11 and row[11] is not None else 0.0,
            'power_fan': row[12] if len(row) > 12 and row[12] is not None else 0.0,
        }

        if latest_primary is None and not is_outdoor_device(point['device_id']):
            latest_primary = point

        if latest_outdoor is None and (
            point['outdoor_temperature'] is not None or is_outdoor_device(point['device_id'])
        ):
            latest_outdoor = point

    if latest_primary is None and rows:
        row = rows[0]
        latest_primary = {
            'time': row[0].isoformat(),
            'device_id': row[1],
            'temperature': row[2],
            'outdoor_temperature': row[3],
            'humidity': row[4],
            'co2': row[5],
            'dust': row[6],
            'power': row[7] if len(row) > 7 and row[7] is not None else 0.0,
            'energy': row[8] if len(row) > 8 and row[8] is not None else 0.0,
            'power_base': row[9] if len(row) > 9 and row[9] is not None else 0.0,
            'energy_base': row[10] if len(row) > 10 and row[10] is not None else 0.0,
            'power_ac': row[11] if len(row) > 11 and row[11] is not None else 0.0,
            'power_fan': row[12] if len(row) > 12 and row[12] is not None else 0.0,
        }

    latest = {
        'temperature': latest_primary.get('temperature') if latest_primary else None,
        'outdoor_temperature': None,
        'humidity': latest_primary.get('humidity') if latest_primary else None,
        'co2': latest_primary.get('co2') if latest_primary else None,
        'dust': latest_primary.get('dust') if latest_primary else None,
        'time': latest_primary.get('time') if latest_primary else None,
        'power': latest_primary.get('power') if latest_primary else 0.0,
        'energy': latest_primary.get('energy') if latest_primary else 0.0,
        'power_base': latest_primary.get('power_base') if latest_primary else 0.0,
        'energy_base': latest_primary.get('energy_base') if latest_primary else 0.0,
        'power_ac': latest_primary.get('power_ac') if latest_primary else 0.0,
        'power_fan': latest_primary.get('power_fan') if latest_primary else 0.0,
    }

    if latest_outdoor:
        latest['outdoor_temperature'] = (
            latest_outdoor.get('outdoor_temperature')
            if latest_outdoor.get('outdoor_temperature') is not None
            else latest_outdoor.get('temperature')
        )

    history = []
    last_indoor_temp = None
    last_outdoor_temp = None
    for row in reversed(rows):
        device_id = row[1]
        indoor_temp = row[2]
        outdoor_temp = row[3]

        if is_outdoor_device(device_id):
            last_outdoor_temp = outdoor_temp if outdoor_temp is not None else indoor_temp
        else:
            last_indoor_temp = indoor_temp
            if outdoor_temp is not None:
                last_outdoor_temp = outdoor_temp

        if last_indoor_temp is None and last_outdoor_temp is None:
            continue

        history.append({
            'time': row[0].strftime('%H:%M:%S'),
            'temp': last_indoor_temp,
            'outdoorTemp': last_outdoor_temp,
            'humidity': row[4],
            'co2': row[5],
            'pm25': row[6],
            'power': row[7] if len(row) > 7 and row[7] is not None else 0.0,
            'energy': row[8] if len(row) > 8 and row[8] is not None else 0.0,
            'power_base': row[9] if len(row) > 9 and row[9] is not None else 0.0,
            'energy_base': row[10] if len(row) > 10 and row[10] is not None else 0.0,
            'power_ac': row[11] if len(row) > 11 and row[11] is not None else 0.0,
            'power_fan': row[12] if len(row) > 12 and row[12] is not None else 0.0,
        })

    control_state = None
    if control_row:
        control_state = {
            'time': control_row[0].isoformat(),
            'device_id': control_row[1],
            'power': control_row[2],
            'temp': control_row[3],
            'operationMode': control_row[4],
            'fanPower': control_row[5],
            'clientId': control_row[6] or 'unknown',
            'requestedAt': control_row[7].isoformat() if control_row[7] else control_row[0].isoformat(),
            'lastModifiedAt': control_row[0].isoformat(),
            'lastModifiedBy': control_row[6] or 'unknown',
            'co2Max': control_row[8] if len(control_row) > 8 and control_row[8] is not None else 800.0,
            'humidityMax': control_row[9] if len(control_row) > 9 and control_row[9] is not None else 60.0,
        }

    # Lấy thông tin AI Zone Manager
    import time
    override_active = time.time() < zone_manager.override_until
    remaining_override = int(zone_manager.override_until - time.time()) if override_active else 0

    return {
        'latest': latest,
        'history': history[-20:],
        'controlState': control_state,
        'zoneManager': {
            'currentPolicy': zone_manager.current_policy,
            'overrideActive': override_active,
            'remainingOverride': remaining_override,
            'scheduledPolicy': zone_manager.get_scheduled_policy(),
            'aiRecommendation': zone_manager.last_recommendation
        }
    }


def save_remote_control_state(command):
    with get_db_connection() as control_conn:
        with control_conn.cursor() as control_cur:
            control_cur.execute("""
                INSERT INTO remote_control_state (time, device_id, power, temp, operation_mode, fan_power, client_id, requested_at, co2_max, humidity_max)
                VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING time, requested_at
            """, (
                command['device_id'],
                command['power'],
                command['temp'],
                command['operationMode'],
                command['fanPower'],
                command['clientId'],
                command['requestedAt'],
                command.get('co2Max', 800.0),
                command.get('humidityMax', 60.0),
            ))
            saved_time, requested_at = control_cur.fetchone()

    return {
        **command,
        'time': saved_time.isoformat(),
        'requestedAt': requested_at.isoformat() if requested_at else saved_time.isoformat(),
        'lastModifiedAt': saved_time.isoformat(),
        'lastModifiedBy': command['clientId'],
        'co2Max': command.get('co2Max', 800.0),
        'humidityMax': command.get('humidityMax', 60.0),
    }

class TelemetryRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_common_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != '/api/telemetry':
            self.send_response(404)
            self.send_common_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Not found'}).encode('utf-8'))
            return

        try:
            body = json.dumps(fetch_telemetry()).encode('utf-8')
            self.send_response(200)
            self.send_common_headers()
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500)
            self.send_common_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != '/api/remote-control':
            self.send_response(404)
            self.send_common_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Not found'}).encode('utf-8'))
            return

        try:
            content_length = int(self.headers.get('Content-Length', '0'))
            raw_body = self.rfile.read(content_length).decode('utf-8')
            payload = json.loads(raw_body or '{}')

            command = {
                'device_id': payload.get('device_id', 'hvac-01'),
                'power': bool(payload.get('power')),
                'temp': to_float(payload.get('temp')),
                'operationMode': payload.get('operationMode'),
                'fanPower': payload.get('fanPower'),
                'co2Max': to_float(payload.get('co2Max')) or 800.0,
                'humidityMax': to_float(payload.get('humidityMax')) or 60.0,
                'clientId': payload.get('clientId') or 'unknown',
                'requestedAt': payload.get('requestedAt') or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            }

            if command['temp'] is None:
                raise ValueError('temp is required')
            if command['operationMode'] not in ['auto', 'cool', 'heat', 'off', 'fan']:
                raise ValueError('operationMode must be auto, cool, heat, off, or fan')
            if command['fanPower'] not in ['auto', 'on', 'off', 'low', 'medium', 'high']:
                raise ValueError('fanPower must be auto, on, off, low, medium, or high')

            # Ghi đè AI Zone Manager bằng lệnh thủ công của người dùng (Manual Override 15 phút)
            if command['clientId'] != "ai-zone-manager":
                zone_manager.override_until = time.time() + 900  # 15 phút
                zone_manager.current_policy = "manual"

            result = client.publish(CONTROL_TOPIC, json.dumps(command), qos=1)
            result.wait_for_publish(timeout=3)

            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f'MQTT publish failed with code {result.rc}')

            saved_command = save_remote_control_state(command)

            body = json.dumps({
                'ok': True,
                'topic': CONTROL_TOPIC,
                'command': saved_command,
            }).encode('utf-8')
            self.send_response(200)
            self.send_common_headers()
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(400)
            self.send_common_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def send_common_headers(self):
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, format, *args):
        return

def start_api_server():
    server = ThreadingHTTPServer((API_HOST, API_PORT), TelemetryRequestHandler)
    print(f"🌐 Telemetry API listening on {API_HOST}:{API_PORT}")
    server.serve_forever()

# ====================== MQTT CALLBACK (Phiên bản mới) ======================
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("✅ Connected to MQTT Broker!")
        client.subscribe("sensor/#")        # Thay đổi topic nếu cần
    else:
        print(f"❌ Connect failed, code: {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        device_id = payload.get('device_id', 'unknown')
        temp = to_float(payload.get('temperature'))
        co2 = to_int(payload.get('co2'))
        humidity = to_float(payload.get('humidity'))
        outdoor_temp = get_outdoor_temperature(payload)

        # 1. Get latest control state for power calculations
        cur.execute("""
            SELECT power, temp, operation_mode, fan_power, co2_max, humidity_max
            FROM remote_control_state
            ORDER BY time DESC
            LIMIT 1
        """)
        c_row = cur.fetchone()
        latest_control = None
        if c_row:
            latest_control = {
                'power': c_row[0],
                'temp': c_row[1],
                'operationMode': c_row[2],
                'fanPower': c_row[3],
                'co2Max': c_row[4],
                'humidityMax': c_row[5],
            }

        # 2. Get previous energy reading and timestamp
        cur.execute("""
            SELECT time, energy_kwh, energy_base_kwh FROM sensor_data
            ORDER BY time DESC
            LIMIT 1
        """)
        prev_row = cur.fetchone()
        
        prev_time = None
        prev_energy = 0.0
        prev_energy_base = 0.0
        if prev_row:
            prev_time = prev_row[0]
            prev_energy = prev_row[1] if prev_row[1] is not None else 0.0
            prev_energy_base = prev_row[2] if len(prev_row) > 2 and prev_row[2] is not None else 0.0

        # 3. Calculate simulated power
        sim_data = calculate_simulated_power(payload, latest_control)
        power_w = sim_data['power_w']
        power_ac_w = sim_data['power_ac_w']
        power_fan_w = sim_data['power_fan_w']
        power_base_w = sim_data['power_base_w']

        # 4. Calculate energy consumption accumulation
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        energy_kwh = prev_energy
        energy_base_kwh = prev_energy_base
        
        if prev_time:
            if prev_time.tzinfo is None:
                prev_time = prev_time.replace(tzinfo=datetime.timezone.utc)
            delta_sec = (now - prev_time).total_seconds()
            if 0 < delta_sec < 3600:
                delta_energy = (power_w * delta_sec) / 3600000.0
                energy_kwh = prev_energy + delta_energy
                
                delta_energy_base = (power_base_w * delta_sec) / 3600000.0
                energy_base_kwh = prev_energy_base + delta_energy_base
            else:
                delta_energy = (power_w * 5.0) / 3600000.0
                energy_kwh = prev_energy + delta_energy
                
                delta_energy_base = (power_base_w * 5.0) / 3600000.0
                energy_base_kwh = prev_energy_base + delta_energy_base
        else:
            energy_kwh = 0.0
            energy_base_kwh = 0.0

        # 5. Insert new sensor data with simulated power and energy
        cur.execute("""
            INSERT INTO sensor_data (time, device_id, temperature, outdoor_temperature, humidity, co2, dust, power_w, energy_kwh, power_base_w, energy_base_kwh, power_ac_w, power_fan_w)
            VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            device_id,
            temp,
            outdoor_temp,
            humidity,
            co2,
            to_float(payload.get('dust')),
            power_w,
            energy_kwh,
            power_base_w,
            energy_base_kwh,
            power_ac_w,
            power_fan_w
        ))
        conn.commit()
        
        print(f"✅ Saved → Device: {device_id} | Temp: {temp} | CO2: {co2} | Power: {power_w:.1f}W | Energy: {energy_kwh:.4f}kWh | BaseEnergy: {energy_base_kwh:.4f}kWh")
        
        # Gọi bộ quản lý Zone tự động đánh giá và điều khiển
        if device_id != 'unknown':
            zone_manager.evaluate_and_control(device_id, temp, co2, humidity, outdoor_temp)
        
    except Exception as e:
        print(f"❌ Error processing message: {e} | Topic: {msg.topic}")

# ====================== MAIN ======================
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)   # ← Sửa ở đây
client.on_connect = on_connect
client.on_message = on_message

# Kết nối client vào zone_manager
zone_manager.set_client(client)

print("🚀 MQTT Subscriber đang chạy...")
Thread(target=start_api_server, daemon=True).start()
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_forever()
