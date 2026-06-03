# ai_mqtt_bridge.py

import json, math, time
import numpy as np
import paho.mqtt.client as mqtt
from datetime import datetime

from drl.ddpg_agent import DDPGAgent, STATE_MIN, STATE_MAX, norm

# ── Cấu hình MQTT ──────────────────────────────────────────
BROKER    = "10.200.5.25"
PORT      = 1883
DEVICE_ID = "indoor-01"
TOPIC_SUB = "sensor/indoor"
TOPIC_PUB = f"remote-control/{DEVICE_ID}"

def rh_to_omega(rh_pct: float, T_c: float) -> float:
    """RH [%] + T [°C] → humidity ratio omega [kg/kg]"""
    p_sat = 0.6112 * math.exp(17.67 * T_c / (T_c + 243.5))  # kPa
    p_v   = (rh_pct / 100.0) * p_sat
    return float(np.clip(0.622 * p_v / (101.325 - p_v), 0.001, 0.030))

def solar_estimate(hour: float) -> float:
    """Bức xạ mặt trời ước tính từ giờ trong ngày [W/m²]"""
    if 6.0 <= hour <= 18.0:
        return max(0.0, 600.0 * math.sin(math.pi * (hour - 6.0) / 12.0))
    return 0.0

def actions_to_commands(a_raw: np.ndarray) -> dict:
    """
    DDPG output [-1,1] → JSON command cho ESP32

    Mapping (Table 5 bài báo → ESP32 semantics):
      a[0]: T_chws_sp ∈ [5,15]°C  → room setpoint ∈ [22,27]°C (nghịch chiều)
      a[1]: D_oa ∈ [20,100]%      → fanPower (damper↑ ≈ fan ON)
      a[2]: f_sa ∈ [10,100]%      → fanPower (fan speed)
      a[3]: P_air ON/OFF          → bỏ qua (không có hardware)
    """
    a = (np.clip(a_raw, -1.0, 1.0) + 1.0) / 2.0  # → [0,1]

    # T_chws_sp: a[0]=0 → 5°C (lạnh nhất) → setpoint phòng thấp nhất (22°C)
    T_chws = 5.0 + a[0] * 10.0                    # [5, 15] °C
    room_sp = round(22.0 + (T_chws - 5.0) / 2.0, 1)  # [22, 27] °C

    # Fan: bật nếu AI muốn fan speed > 20% HOẶC damper > 30%
    f_sa  = 0.1 + a[2] * 0.9   # [0.1, 1.0]
    D_oa  = 0.2 + a[1] * 0.8   # [0.2, 1.0]
    fan_on = (f_sa > 0.20) or (D_oa > 0.30)

    # Operation mode: cooling mạnh khi T_chws < 10°C
    op_mode = "cool" if T_chws < 10.0 else "auto"

    return {
        "device_id":     DEVICE_ID,
        "temp":          room_sp,          # TEMP_SETPOINT trên ESP32
        "fanPower":      "on" if fan_on else "off",
        "operationMode": op_mode,
        "power":         True
    }

# ── AI Bridge class ─────────────────────────────────────────
class AIBridge:
    def __init__(self, checkpoint: str = "checkpoints"):
        # Load DDPG agent (inference only, no training)
        self.agent = DDPGAgent(state_dim=10, action_dim=4)
        self.agent.load(checkpoint)
        print(f"[AI] Loaded DDPG from '{checkpoint}/'")

        self.client = mqtt.Client(client_id="ai-bridge-hvac")
        self.client.on_connect    = self._on_connect
        self.client.on_message    = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self._last_pub_time = 0
        self.MIN_PUB_INTERVAL = 15  # giây — tránh spam lệnh

    # ── MQTT callbacks ──────────────────────────────────────
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(TOPIC_SUB)
            print(f"[MQTT] ✓ Connected | Subscribed: {TOPIC_SUB}")
        else:
            print(f"[MQTT] ✗ Connect failed rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        print(f"[MQTT] Disconnected rc={rc}. Auto-reconnect...")

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            if data.get("device_id") != DEVICE_ID:
                return           # bỏ qua thiết bị khác

            # Rate limiting: không publish quá mỗi 15 giây
            now = time.time()
            if now - self._last_pub_time < self.MIN_PUB_INTERVAL:
                return
            self._last_pub_time = now

            self._run_inference(data)

        except Exception as e:
            print(f"[Error] on_message: {e}")

    # ── Inference pipeline ──────────────────────────────────
    def _run_inference(self, data: dict):
        # 1. Trích xuất dữ liệu từ SCD30
        T_za  = float(data.get("temperature",          25.0))
        rh_za = float(data.get("humidity",             50.0))  # %
        co2   = float(data.get("co2",                 600.0))  # ppm
        # outdoor_temperature hiện tại = T_za + 3.2 (xem HVAC_Control.ino)
        T_oa  = float(data.get("outdoor_temperature", T_za + 3.0))
        dust  = float(data.get("dust",                 10.0))  # μg/m³

        # 2. Tính toán biến dẫn xuất
        omega_za = rh_to_omega(rh_za, T_za)
        omega_oa = rh_to_omega(max(rh_za - 5, 20), T_oa)  # ước lượng outdoor RH

        hour   = datetime.now().hour + datetime.now().minute / 60.0
        q_sol  = solar_estimate(hour)
        pm_out = dust                       # dust từ ESP32 ≈ C_PM_oa
        pm_in  = max(0.0, dust * 0.75)     # indoor PM2.5 ≈ 75% outdoor (giả định)

        # 3. Xây dựng state vector (10 chiều — khớp với training)
        state = np.array([
            hour,       # time of day [0,24]
            T_oa,       # outdoor temperature [°C]
            omega_oa,   # outdoor humidity ratio [kg/kg]
            q_sol,      # solar irradiance [W/m²]
            450.0,      # outdoor CO2 [ppm] — cố định
            pm_out,     # outdoor PM2.5 [μg/m³]
            T_za,       # zone temperature [°C]    ← từ SCD30
            omega_za,   # zone humidity ratio      ← tính từ SCD30
            co2,        # zone CO2 [ppm]           ← từ SCD30
            pm_in,      # zone PM2.5 [μg/m³]      ← ước lượng
        ], dtype=np.float32)

        # 4. DDPG inference (deterministic, no noise)
        action  = self.agent.select_action(norm(state), add_noise=False)
        command = actions_to_commands(action)

        # 5. Publish lệnh điều khiển
        payload = json.dumps(command)
        self.client.publish(TOPIC_PUB, payload, qos=1)

        # 6. Log
        ts = datetime.now().strftime("%H:%M:%S")
        a_sim = (np.clip(action, -1, 1) + 1) / 2
        print(
            f"[{ts}] IN: T={T_za:.1f}°C RH={rh_za:.0f}% CO2={co2:.0f}ppm | "
            f"OUT→ sp={command['temp']}°C fan={command['fanPower']:3s} "
            f"mode={command['operationMode']} | "
            f"[T_chws={5+a_sim[0]*10:.1f}°C f_sa={10+a_sim[2]*90:.0f}%]"
        )

    # ── Start ───────────────────────────────────────────────
    def run(self):
        print(f"[AI Bridge] Connecting {BROKER}:{PORT} ...")
        self.client.connect(BROKER, PORT, keepalive=60)
        self.client.loop_forever()   # blocking, tự reconnect


if __name__ == "__main__":
    bridge = AIBridge(checkpoint="checkpoints_v2")
    bridge.run()
