/**
 * HVAC_Control_v1.ino
 * 
 * HỆ THỐNG ĐIỀU KHIỂN HVAC THÔNG MINH - HOÀN THIỆN TÍCH HỢP DASHBOARD
 * Thiết kế cho: ESP32-S3-N16R8 + Sensirion SCD30 + Module Relay
 * Nền tảng: Arduino IDE
 * 
 * Tính năng chính:
 *   1. Tự động kiểm soát nhiệt độ (Làm mát/Làm ấm qua hệ thống LED chỉ thị)
 *   2. Tự động điều khiển quạt tản thông gió qua Relay (khi CO2 > 1000 ppm hoặc Độ ẩm > 60%)
 *   3. Kết nối WiFi và đồng bộ hóa dữ liệu 2 chiều với Dashboard qua giao thức MQTT:
 *      - Chiều gửi: Đẩy thông số cảm biến lên topic "sensor/hvac-01" dạng JSON.
 *      - Chiều nhận: Lắng nghe lệnh điều khiển tắt/bật nguồn, thay đổi nhiệt độ cài đặt từ xa qua topic "remote-control".
 *   4. Cơ chế tự động hóa cục bộ độc lập: Nếu mất mạng WiFi/MQTT, hệ thống cục bộ vẫn tự điều khiển an toàn!
 * 
 * v1: Thêm hiển thị chi tiết lệnh nhận được từ MQTT (tóm tắt sau parse)
 */

#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <SparkFun_SCD30_Arduino_Library.h>
// #include "../libraries/SparkFun_SCD30/SparkFun_SCD30_Arduino_Library.h"
// #include "../libraries/PubSubClient/PubSubClient.h"

// ⚙️ CẤU HÌNH HỆ THỐNG
#define WIFI_SSID          "zzzz"
#define WIFI_PASSWORD      "12345678"

#define MQTT_SERVER        "10.51.27.198"
#define MQTT_PORT          1883
#define MQTT_DEVICE_ID     "indoor-01"
#define MQTT_PUB_TOPIC     "state"
#define MQTT_SUB_TOPIC     "action"

#define OWM_FETCH_INTERVAL 600000UL             // Chu kỳ lấy dữ liệu OWM (10 phút = 600.000 ms)

// 3. Cấu hình chân kết nối phần cứng (Pin Definitions)
#define USE_ONBOARD_RGB  true  // Đặt thành 'true' nếu dùng LED RGB WS2812B tích hợp trên board ESP32-S3
#define PIN_RGB_WS2812   48    // Chân điều khiển LED RGB WS2812B (thường là 48 hoặc 38)
#define I2C_SDA          8     // Chân SDA nối cảm biến SCD30
#define I2C_SCL          9     // Chân SCL nối cảm biến SCD30
#define PIN_PMS_RX       16    // Chân RX1 nối với PMS_TX (GPIO16)
#define PIN_PMS_TX       17    // Chân TX1 nối với PMS_RX (GPIO17)
// #define PIN_RELAY_FAN    4     // Chân GPIO4 điều khiển Relay quạt tản
// #define RELAY_ACTIVE_LOW false // Sửa lỗi ngược: Đặt thành false (Kích HIGH để bật quạt, LOW để tắt)hái nhiệt độ
// #define PIN_SERVO        15    // Chân tín hiệu điều khiển van thông gió Servo (GPIO15)

// Các chân GPIO nếu bạn sử dụng LED rời gắn ngoài (khi USE_ONBOARD_RGB = false)
#define PIN_LED_COOLING  10    // LED Xanh báo làm mát (Cooling)
#define PIN_LED_HEATING  11    // LED Đỏ hoặc màu khác báo làm ấm (Heating)

// // Cấu hình LEDC cho Servo
// #define SERVO_LEDC_CH    0     // Kênh LEDC cho Servo
// #define SERVO_LEDC_HZ    50    // Tần số PWM cho Servo (50Hz)
// #define SERVO_LEDC_RES   12    // Độ phân giải 12-bit

// 🔄 THÔNG SỐ VÀ BIẾN TOÀN CỤC
SCD30 airSensor;
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Các biến điều khiển hệ thống (Có thể thay đổi động từ xa qua MQTT)
float TEMP_SETPOINT     = 25.0; // Nhiệt độ cài đặt mục tiêu (°C)
bool  systemPowerState  = true; // Trạng thái hoạt động hệ thống (true: ON, false: OFF - Chế độ chờ Standby)
float systemDamperRatio = 0.3;  // Tỷ lệ mở van thông gió từ 0.2 đến 1.0 (20% - 100%)
float latestPM25        = 12.5; // Giá trị bụi mịn PM2.5 (ug/m3) đo từ PMS7003

// Các ngưỡng cố định bảo vệ tiện nghi không khí
const float TEMP_HYSTERESIS     = 0.5;   // Khoảng trễ nhiệt độ (°C) tránh đóng ngắt liên tục
const float CO2_HYSTERESIS      = 100.0; // Khoảng trễ CO2 (Quạt tắt khi < CO2_MAX - 100)
float CO2_MAX                   = 800.0;  // Ngưỡng CO2 chuẩn báo động (ppm) để bật quạt (có thể thay đổi động)
const float HUMIDITY_HYSTERESIS = 5.0; // Khoảng trễ độ ẩm (Quạt tắt khi < HUMIDITY_MAX - 5)
float HUMIDITY_MAX              = 60.0;  // Ngưỡng độ ẩm tối đa (%) theo chuẩn (có thể thay đổi động)
const float PM25_HYSTERESIS     = 5.0;   // Khoảng trễ PM2.5 (Quạt tắt khi < PM25_MAX - 5)
float PM25_MAX                  = 35.0;  // Ngưỡng bụi mịn PM2.5 chuẩn báo động (ug/m3) để bật quạt (có thể thay đổi động)

// Quản lý trạng thái hiện tại
bool currentFanState   = false; // Trạng thái Quạt tản (false: OFF, true: ON)
bool isCoolingActive   = false; // Trạng thái Làm mát
bool isHeatingActive   = false; // Trạng thái Làm ấm

// Các biến điều khiển hệ thống nâng cao
String hvacMode        = "auto";
String hvacManualState = "off";
String fanMode         = "auto";
String fanManualState  = "off";

unsigned long lastReadTime              = 0;
const unsigned long READ_INTERVAL       = 10000;
unsigned long lastMqttRetryTime         = 0;
const unsigned long MQTT_RETRY_INTERVAL = 5000;
// ── BIẾN TOÀN CỤC LƯU DỮ LIỆU THỜI TIẾT ─────────────────
float g_out_temp   = 0.0;   // Nhiệt độ ngoài trời (°C)
float g_out_rh     = 0.0;   // Độ ẩm ngoài trời (%)
float g_wind       = 0.0;   // Tốc độ gió (m/s)
bool  owmDataValid = false; // true khi đã có dữ liệu OWM hợp lệ

// 🛠️ CÁC HÀM TIỆN ÍCH ĐIỀU KHIỂN THIẾT BỊ
/* Hàm đọc và giải mã không chặn dữ liệu từ cảm biến bụi mịn PMS7003 qua Serial */
bool readPMS7003(float &pm25_val) {
  static uint8_t buffer[32];
  static uint8_t index = 0;
  
  while (Serial1.available() > 0) {
    uint8_t ch = Serial1.read();
    // Tìm byte bắt đầu 0x42
    if (index == 0 && ch != 0x42) continue;
    // Tìm byte bắt đầu 0x4d
    if (index == 1 && ch != 0x4d) {
      index = 0;
      continue;
    }
    
    buffer[index++] = ch;
    
    if (index == 32) {
      index = 0; // Reset index cho lần đọc tiếp theo
      // Tính toán Checksum
      uint16_t sum = 0;
      for (int i = 0; i < 30; i++) {
        sum += buffer[i];
      }
      uint16_t checksum = (buffer[30] << 8) | buffer[31];
      
      if (sum == checksum) {
        // PM2.5 trong môi trường khí quyển (Atmos) nằm ở bytes 12 và 13
        uint16_t pm25_atm = (buffer[12] << 8) | buffer[13];
        pm25_val = (float)pm25_atm;
        return true;
      }
    }
  }
  return false;
}

/* Hàm điều khiển hệ thống LED chỉ thị nhiệt độ */
void controlTemperatureLEDs(bool cooling, bool heating) {
  isCoolingActive = cooling;
  isHeatingActive = heating;
  if (USE_ONBOARD_RGB) {
    if (cooling) {
      neopixelWrite(PIN_RGB_WS2812, 0, 0, 128);
    } else if (heating) {
      neopixelWrite(PIN_RGB_WS2812, 128, 0, 0);
    } else {
      neopixelWrite(PIN_RGB_WS2812, 0, 0, 0);
    }
  } else {
    digitalWrite(PIN_LED_COOLING, cooling ? HIGH : LOW);
    digitalWrite(PIN_LED_HEATING, heating ? HIGH : LOW);
  }
}

// /* Hàm bật/tắt Relay Quạt tản */
// void controlFan(bool turnOn) {
//   currentFanState = turnOn;
//   if (RELAY_ACTIVE_LOW) {
//     digitalWrite(PIN_RELAY_FAN, turnOn ? LOW : HIGH);
//   } else {
//     digitalWrite(PIN_RELAY_FAN, turnOn ? HIGH : LOW);
//   }
// }

// /* Hàm điều khiển góc mở van thông gió Servo qua PWM */
// void controlVentilationDamper(float ratio) {
//   ratio = constrain(ratio, 0.0, 1.0);
//   int angle = (int)(ratio * 90.0); // Quy đổi góc từ 0 đến 90 độ
  
//   // Tính toán chu kỳ xung cho Servo (50Hz -> 20ms)
//   // Duty cycle 12-bit (0-4095): 0.5ms (0 độ) = 102, 2.5ms (180 độ) = 512
//   int duty = map(angle, 0, 180, 102, 512);
//   ledcWrite(SERVO_LEDC_CH, duty);
// }

// 🌐 KẾT NỐI MẠNG (WIFI & MQTT)
/* Hàm khởi tạo kết nối WiFi ban đầu */
void setupWiFi() {
  delay(10);
  Serial.print("\n[WiFi] Dang ket noi toi mang: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 15) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Ket noi thanh cong!");
    Serial.print("[WiFi] Dia chi IP cua ESP32: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[Canh bao] Khong the ket noi WiFi. He thong se chay o che do CUC BO (Offline).");
  }
}

// /** Bộ xử lý tin nhắn điều khiển từ xa (MQTT Callback) **/
// void mqttCallback(char* topic, byte* payload, unsigned int length) {
//   char message[256];
//   unsigned int i = 0;
//   for (i = 0; i < length && i < sizeof(message) - 1; i++) {
//     message[i] = (char)payload[i];
//   }
//   message[i] = '\0';

//   // ── In raw payload nhận được ─────────────────────────
//   Serial.printf("\n[MQTT Callback] Nhan lenh tren Topic [%s]: %s\n", topic, message);

//   // Lưu trạng thái cũ để so sánh
//   bool     old_power    = systemPowerState;
//   float    old_temp     = TEMP_SETPOINT;
//   String   old_hvacMode = hvacMode;
//   String   old_fanMode  = fanMode;
//   float    old_co2Max   = CO2_MAX;
//   float    old_humMax   = HUMIDITY_MAX;

//   // 1. POWER
//   char* powerPtr = strstr(message, "\"power\"");
//   if (powerPtr != NULL) {
//     char* valPtr = strchr(powerPtr, ':');
//     if (valPtr != NULL) {
//       valPtr++;
//       while (*valPtr == ' ' || *valPtr == '\t') valPtr++;
//       bool nextPowerState = systemPowerState;
//       if (strncmp(valPtr, "true", 4) == 0)        nextPowerState = true;
//       else if (strncmp(valPtr, "false", 5) == 0)  nextPowerState = false;

//       if (nextPowerState != systemPowerState) {
//         systemPowerState = nextPowerState;
//         Serial.printf("  --> [MQTT Command] Thay doi nguon he thong: %s\n", 
//                       systemPowerState ? "BAT (ON)" : "TAT (STANDBY/OFF)");
//         if (!systemPowerState) {
//           controlFan(false);
//           controlTemperatureLEDs(false, false);
//           if (USE_ONBOARD_RGB) neopixelWrite(PIN_RGB_WS2812, 10, 5, 0);
//         }
//       }
//     }
//   }

//   // 2. TEMP SETPOINT
//   char* tempPtr = strstr(message, "\"temp\"");
//   if (tempPtr != NULL) {
//     char* valPtr = strchr(tempPtr, ':');
//     if (valPtr != NULL) {
//       valPtr++;
//       float newSetpoint = atof(valPtr);
//       if (newSetpoint >= 0.0 && newSetpoint <= 40.0) {
//         TEMP_SETPOINT = newSetpoint;
//         Serial.printf("  --> [MQTT Command] Cap nhat Setpoint nhiet do moi: %.1f *C\n", TEMP_SETPOINT);
//       } else {
//         Serial.printf("  --> [MQTT Command] Canh bao: Nhiet do %.1f *C ngoai dải an toan (0 - 40*C)\n", newSetpoint);
//       }
//     }
//   }

//   // 3. HVAC OPERATION MODE
//   char* opModePtr = strstr(message, "\"operationMode\"");
//   if (opModePtr != NULL) {
//     char* valPtr = strchr(opModePtr, ':');
//     if (valPtr != NULL) {
//       valPtr++;
//       while (*valPtr == ' ' || *valPtr == '\t' || *valPtr == '"') valPtr++;
//       if      (strncmp(valPtr, "auto", 4) == 0) { hvacMode = "auto"; }
//       else if (strncmp(valPtr, "cool", 4) == 0) { hvacMode = "manual"; hvacManualState = "cool"; }
//       else if (strncmp(valPtr, "heat", 4) == 0) { hvacMode = "manual"; hvacManualState = "heat"; }
//       else if (strncmp(valPtr, "off",  3) == 0) { hvacMode = "manual"; hvacManualState = "off";  }
//       Serial.printf("  --> [MQTT Command] HVAC Mode: %s | State: %s\n", hvacMode.c_str(), hvacManualState.c_str());
//     }
//   }

//   // 4. FAN POWER
//   char* fanPowerPtr = strstr(message, "\"fanPower\"");
//   if (fanPowerPtr != NULL) {
//     char* valPtr = strchr(fanPowerPtr, ':');
//     if (valPtr != NULL) {
//       valPtr++;
//       while (*valPtr == ' ' || *valPtr == '\t' || *valPtr == '"') valPtr++;
//       if      (strncmp(valPtr, "auto", 4) == 0) { fanMode = "auto"; }
//       else if (strncmp(valPtr, "on",   2) == 0) { fanMode = "manual"; fanManualState = "on";  }
//       else if (strncmp(valPtr, "off",  3) == 0) { fanMode = "manual"; fanManualState = "off"; }
//       Serial.printf("  --> [MQTT Command] Fan Mode: %s | State: %s\n", fanMode.c_str(), fanManualState.c_str());
//     }
//   }

//   // 5. CO2 MAX
//   char* co2MaxPtr = strstr(message, "\"co2Max\"");
//   if (co2MaxPtr != NULL) {
//     char* valPtr = strchr(co2MaxPtr, ':');
//     if (valPtr != NULL) {
//       valPtr++;
//       float newCo2Max = atof(valPtr);
//       if (newCo2Max >= 400.0 && newCo2Max <= 2000.0) {
//         CO2_MAX = newCo2Max;
//         Serial.printf("  --> [MQTT Command] Cap nhat nguong CO2 an toan: %.1f ppm\n", CO2_MAX);
//       }
//     }
//   }

//   // 6. HUMIDITY MAX
//   char* humMaxPtr = strstr(message, "\"humidityMax\"");
//   if (humMaxPtr != NULL) {
//     char* valPtr = strchr(humMaxPtr, ':');
//     if (valPtr != NULL) {
//       valPtr++;
//       float newHumMax = atof(valPtr);
//       if (newHumMax >= 10.0 && newHumMax <= 95.0) {
//         HUMIDITY_MAX = newHumMax;
//         Serial.printf("  --> [MQTT Command] Cap nhat nguong do am an toan: %.1f %\n", HUMIDITY_MAX);
//       }
//     }
//   }

//   // 7. DAMPER
//   char* damperPtr = strstr(message, "\"damper\"");
//   if (damperPtr != NULL) {
//     char* valPtr = strchr(damperPtr, ':');
//     if (valPtr != NULL) {
//       valPtr++;
//       float newDamper = atof(valPtr);
//       if (newDamper >= 0.0 && newDamper <= 1.0) {
//         systemDamperRatio = newDamper;
//         Serial.printf("  --> [MQTT Command] Cap nhat do mo van: %.2f\n", systemDamperRatio);
//       }
//     }
//   }

//   // ── [v1] In bảng tóm tắt sau khi parse xong ───────────────
//   Serial.println("  Ket qua parse:");
//   Serial.printf( "    Power        : %s  %s\n",
//                  systemPowerState ? "ON " : "OFF",
//                  systemPowerState != old_power ? "<-- DA THAY DOI" : "");
//   Serial.printf( "    Temp setpoint: %.1f *C  %s\n",
//                  TEMP_SETPOINT,
//                  TEMP_SETPOINT != old_temp ? "<-- DA THAY DOI" : "");
//   Serial.printf( "    HVAC mode    : %s  (state: %s)  %s\n",
//                  hvacMode.c_str(), hvacManualState.c_str(),
//                  hvacMode != old_hvacMode ? "<-- DA THAY DOI" : "");
//   Serial.printf( "    Fan mode     : %s  (state: %s)  %s\n",
//                  fanMode.c_str(), fanManualState.c_str(),
//                  fanMode != old_fanMode ? "<-- DA THAY DOI" : "");
//   Serial.printf( "    CO2 max      : %.0f ppm  %s\n",
//                  CO2_MAX,
//                  CO2_MAX != old_co2Max ? "<-- DA THAY DOI" : "");
//   Serial.printf( "    Humidity max : %.0f %%  %s\n",
//                  HUMIDITY_MAX,
//                  HUMIDITY_MAX != old_humMax ? "<-- DA THAY DOI" : "");
//   Serial.println("╚══════════════════════════════════════════════════════╝\n");
//   // ──────────────────────────────────────────────────────────
// }

/* Hàm tự động duy trì và kết nối lại WiFi khi mất mạng */
void maintainWiFiConnection() {
  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long lastWiFiRetryTime = 0;
    unsigned long now = millis();
    if (now - lastWiFiRetryTime >= 10000) {
      lastWiFiRetryTime = now;
      Serial.println("\n[WiFi] Canh bao: Mat ket noi! Dang ket noi lai WiFi...");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
  }
}
/* Hàm duy trì và kết nối lại MQTT Broker (Không chặn luồng chính) */
void maintainMQTTConnection() {
  if (!mqttClient.connected()) {
    unsigned long now = millis();
    if (now - lastMqttRetryTime >= MQTT_RETRY_INTERVAL) {
      lastMqttRetryTime = now;
      if (WiFi.status() == WL_CONNECTED) {
        Serial.print("[MQTT] Dang ket noi den Broker...");
        if (mqttClient.connect(MQTT_DEVICE_ID)) {
          Serial.println("Thanh cong!");
          mqttClient.subscribe(MQTT_SUB_TOPIC);
          Serial.printf("[MQTT] Da subscribe topic: %s\n", MQTT_SUB_TOPIC);
        } else {
          Serial.printf("That bai, rc = %d. Thu lai sau 5 giay.\n", mqttClient.state());
        }
      } else {
        Serial.println("[MQTT] WiFi chua online. Bo qua.");
      }
    }
  } else {
    mqttClient.loop();
  }
}

// 2. Thay bằng API Key lấy từ OpenWeatherMap của bạn
const String apiKey = "88f5822bdd8e934a4c4f7f6b5dac85c0"; 
const String city = "Hanoi";
const String countryCode = "VN";
// Hàm xử lý gọi API và giải mã dữ liệu thời tiết
void layDuLieuThoiTiet() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[Weather] WiFi offline, bo qua lay thoi tiet.");
    return;
  }

  HTTPClient http;
  // Đường dẫn API lấy thời tiết Hà Nội (đơn vị Độ C)
  String serverPath = "http://api.openweathermap.org/data/2.5/weather?q="
                      + city + "," + countryCode
                      + "&appid=" + apiKey + "&units=metric";  
  Serial.println("[Weather] Dang lay du lieu thoi tiet ngoai troi...");
  http.begin(serverPath);
  int httpCode = http.GET();
  
  if (httpCode == 200) {
    String payload = http.getString();
    // Khởi tạo bộ giải mã JSON (Cú pháp chuẩn cho ArduinoJson V7)
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, payload);

    if (!error) {
      g_out_temp = doc["main"]["temp"];        // °C
      g_out_rh   = doc["main"]["humidity"];    // %
      g_wind     = doc["wind"]["speed"];       // m/s

      Serial.printf("[Weather] out_temp=%.1f*C | out_rh=%.0f%% | wind=%.1fm/s\n",
                    g_out_temp, g_out_rh, g_wind);
    } else {
      Serial.printf("[Weather] Loi giai ma JSON: %s\n", error.c_str());
    }
  } else {
    Serial.printf("[Weather] Loi HTTP %d\n", httpCode);
  }
  http.end(); // Giải phóng tài nguyên HTTP
}

// SETUP & LOOP
void setup() {
  Serial.begin(115200);
  delay(2000);

  Serial.println("\n=======================================================");
  Serial.println("  KHOI DONG SAN PHAM HVAC CONTROL SMART-IOT COMPLETED");
  Serial.println("=======================================================");

  // 1. Cấu hình chân phần cứng Output
  // pinMode(PIN_RELAY_FAN, OUTPUT);
  // controlFan(false); // Quạt tắt ban đầu

  if (!USE_ONBOARD_RGB) {
    pinMode(PIN_LED_COOLING, OUTPUT);
    pinMode(PIN_LED_HEATING, OUTPUT);
    digitalWrite(PIN_LED_COOLING, LOW);
    digitalWrite(PIN_LED_HEATING, LOW);
  } else {
    neopixelWrite(PIN_RGB_WS2812, 0, 0, 0); // Tắt LED RGB
  }

  // 2. Khởi tạo bus I2C tùy biến
  Serial.printf("[I2C] Khoi tao bus: SDA -> GPIO%d, SCL -> GPIO%d...\n", I2C_SDA, I2C_SCL);
  Wire.begin(I2C_SDA, I2C_SCL);

  // 3. Khởi tạo cảm biến SCD30
  Serial.println("[SCD30] Dang ket noi voi cam bien...");
  if (airSensor.begin(Wire) == false) {
    Serial.println("[LOI] Khong tim thay cam bien SCD30!");
    Serial.println("  --> Vui long kiem tra lai duong day va nguon cap.");
  } else {
    Serial.println("[SCD30] Ket noi thanh cong!");
    airSensor.setMeasurementInterval(2);
  }

  setupWiFi();

  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  // mqttClient.setCallback(mqttCallback);

  Serial.println("\n>> He thong HVAC san sang hoat dong!");
  Serial.println("-------------------------------------------------------");
}

void loop() {
  // Đọc dữ liệu từ cảm biến bụi mịn PMS7003 liên tục
  readPMS7003(latestPM25);
  maintainWiFiConnection();
  maintainMQTTConnection();

  unsigned long now = millis();
  if (now - lastReadTime >= READ_INTERVAL) {
    lastReadTime = now;

    float in_temp = airSensor.getTemperature();
    float in_rh   = airSensor.getHumidity();
    float co2     = airSensor.getCO2();

    // ── [2] Lấy thời tiết, kết quả ghi vào g_out_temp / g_out_rh / g_wind
    layDuLieuThoiTiet();

    Serial.printf("[Sensor] CO2: %.1f ppm | in_temp: %.1f*C | in_rh: %.1f%% | "
                  "out_temp: %.1f*C | out_rh: %.0f%% | wind: %.1f m/s\n",
                  co2, in_temp, in_rh, g_out_temp, g_out_rh, g_wind);

    // if (systemPowerState) {
    //   // ── THUẬT TOÁN ĐIỀU KHIỂN NHIỆT ĐỘ ─────────────────────
    //   bool nextCoolingState = isCoolingActive;
    //   bool nextHeatingState = isHeatingActive;

    //   if (hvacMode == "auto") {
    //     if      (temperature > (TEMP_SETPOINT + TEMP_HYSTERESIS / 2.0)) { nextCoolingState = true;  nextHeatingState = false; }
    //     else if (temperature < (TEMP_SETPOINT - TEMP_HYSTERESIS / 2.0)) { nextCoolingState = false; nextHeatingState = true;  }
    //   } else {
    //     nextCoolingState = (hvacManualState == "cool");
    //     nextHeatingState = (hvacManualState == "heat");
    //   }

    //   if (nextCoolingState != isCoolingActive || nextHeatingState != isHeatingActive) {
    //     controlTemperatureLEDs(nextCoolingState, nextHeatingState);
    //     Serial.printf("  --> [LED] %s\n",
    //                   nextCoolingState ? "LAM MAT (XANH)" : (nextHeatingState ? "LAM AM (DO)" : "TAT"));
    //   }

    //   // ── THUẬT TOÁN ĐIỀU KHIỂN QUẠT ──────────────────────────
    //   bool nextFanState = currentFanState;

    //   if (fanMode == "auto") {
    //     if      (co2 > CO2_MAX || humidity > HUMIDITY_MAX)                                    nextFanState = true;
    //     else if (co2 < (CO2_MAX - CO2_HYSTERESIS) && humidity < (HUMIDITY_MAX - HUMIDITY_HYSTERESIS)) nextFanState = false;
    //   } else {
    //     nextFanState = (fanManualState == "on");
    //   }

    //   if (nextFanState != currentFanState) {
    //     controlFan(nextFanState);
    //     Serial.printf("  --> [QUAT] %s\n", nextFanState ? "ON" : "OFF");
    //   }
    // } else {
    //   Serial.println("  --> [System] Standby. Cho lenh tu xa...");
    // }

    // ── PUBLISH DỮ LIỆU CẢM BIẾN ────────────────────────────
    if (mqttClient.connected()) {
      char jsonPayload[256];
      snprintf(jsonPayload, sizeof(jsonPayload),
               "{"
                 "\"device_id\":\"%s\","
                 "\"in_temp\":%.2f,"
                 "\"in_rh\":%.2f,"
                 "\"out_temp\":%.2f,"
                 "\"out_rh\":%.2f,"
                 "\"CO2\":%.1f,"
                 "\"dust\":%.1f,"
                 "\"wind\":%.2f"
               "}",
               MQTT_DEVICE_ID,
               in_temp, in_rh,        // từ SCD30
               g_out_temp,  g_out_rh, // từ OpenWeatherMap
               co2,                   // ppm– từ SCD30
               latestPM25,            // µg/m³ – từ cảm biến bụi
               g_wind                 // m/s– từ OpenWeatherMap
      );
      Serial.printf("[MQTT Publish] Topic [%s]: %s\n", MQTT_PUB_TOPIC, jsonPayload);
      bool ok = mqttClient.publish(MQTT_PUB_TOPIC, jsonPayload);
      Serial.printf("  --> %s\n", ok ? "OK" : "LOI: Gui that bai");
    } else {
      Serial.println("[MQTT] Offline. Bo qua gui du lieu.");
    }
  }
}