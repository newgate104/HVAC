/**
 * SCD30_Test.ino
 * 
 * Chương trình kiểm tra hoạt động của cảm biến Sensirion SCD30 với ESP32-S3-N16R8.
 * Kết nối chân I2C tùy biến:
 *   - SDA -> GPIO8
 *   - SCL -> GPIO9
 * 
 * Hướng dẫn sử dụng:
 *   1. Đảm bảo đã cài đặt thư viện "SparkFun SCD30 Arduino Library".
 *   2. Nạp code này vào board ESP32-S3.
 *   3. Mở Serial Monitor với tốc độ baud là 115200.
 */

#include <Wire.h>
#include "src/SparkFun_SCD30/SparkFun_SCD30_Arduino_Library.h" // Thư viện SparkFun SCD30

// Định nghĩa chân I2C cho ESP32-S3-N16R8
#define I2C_SDA 8
#define I2C_SCL 9

SCD30 airSensor;

void setup() {
  // Khởi tạo Serial Monitor
  Serial.begin(115200);
  
  // Đối với cổng USB Native của ESP32-S3, cần đợi một lúc để Serial sẵn sàng
  delay(2000); 
  
  Serial.println("\n=============================================");
  Serial.println("   KHOI TONG KIEM TRA CAM BIEN SENSIRION SCD30");
  Serial.println("=============================================");
  
  // Khởi tạo kết nối I2C tùy chỉnh
  Serial.printf("Khoi tao I2C: SDA = GPIO%d, SCL = GPIO%d...\n", I2C_SDA, I2C_SCL);
  bool i2cStatus = Wire.begin(I2C_SDA, I2C_SCL);
  
  if (!i2cStatus) {
    Serial.println("Loi: Khong the khoi tao I2C bus!");
    while (1) { delay(1000); }
  }

  // Khởi tạo cảm biến SCD30 với bus I2C tùy chỉnh
  Serial.println("Dang ket noi voi SCD30...");
  if (airSensor.begin(Wire) == false) {
    Serial.println("Loi: Khong tim thay cam bien SCD30!");
    Serial.println("Vui long kiem tra lai: Sơ đồ dau noi, Nguon 3.3V, Day SDA va SCL.");
    while (1) {
      delay(1000);
    }
  }

  Serial.println("Ket noi thanh cong voi cam bien SCD30!");
  
  // Cài đặt tần suất đo (mặc định SCD30 đo 2 giây một lần)
  airSensor.setMeasurementInterval(2);
  Serial.println("Bat dau lay du lieu moi 2 giay...");
  Serial.println("---------------------------------------------");
  Serial.println("CO2 (ppm) \tNhiet do (C) \tDo am (%)");
  Serial.println("---------------------------------------------");
}

void loop() {
  // Kiem tra xem co du lieu moi tu cam bien khong
  if (airSensor.dataAvailable()) {
    float co2 = airSensor.getCO2();
    float temp = airSensor.getTemperature();
    float hum = airSensor.getHumidity();

    // In ket qua ra Serial Monitor
    Serial.print(co2, 1);
    Serial.print(" ppm\t\t");
    
    Serial.print(temp, 1);
    Serial.print(" C\t\t");
    
    Serial.print(hum, 1);
    Serial.println(" %");
  } else {
    // Neu cam bien chua san sang, doi mot chut
    delay(100);
  }
}
