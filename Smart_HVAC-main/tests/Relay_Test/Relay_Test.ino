/**
 * Relay_Test.ino
 * 
 * Chương trình kiểm tra hoạt động của Module Relay điều khiển Quạt tản với ESP32-S3.
 * Kết nối chân điều khiển:
 *   - IN1 (Relay Control) -> GPIO4
 * 
 * Logic hoạt động:
 *   - Bật Relay (Quạt chạy) trong 5 giây, đèn LED onboard báo hiệu.
 *   - Tắt Relay (Quạt tắt) trong 5 giây, tắt đèn báo hiệu.
 *   - Chu kỳ lặp đi lặp lại liên tục.
 *   - In trạng thái chi tiết ra Serial Monitor.
 */

// =========================================================================
// ⚙️ CẤU HÌNH CHÂN KẾT NỐI
// =========================================================================
#define PIN_RELAY_FAN    4     // Chân GPIO4 điều khiển Relay quạt tản

// Hầu hết các Module Relay trên thị trường kích hoạt ở mức THẤP (Active LOW - kích bằng 0V)
// Nếu Relay của bạn kích hoạt ở mức CAO (Active HIGH - kích bằng 3.3V/5V), hãy sửa thành false
#define RELAY_ACTIVE_LOW true  

void setup() {
  // Khởi tạo Serial Monitor
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n=============================================");
  Serial.println("   KHOI TONG KIEM TRA MODULE RELAY QUAT TAN");
  Serial.println("=============================================");
  Serial.printf("Chan dieu khien Relay: GPIO%d\n", PIN_RELAY_FAN);
  Serial.printf("Che do kich hoat: %s\n", RELAY_ACTIVE_LOW ? "Active LOW (Muc THAP)" : "Active HIGH (Muc CAO)");
  
  // Khởi tạo chân GPIO điều khiển Relay là OUTPUT
  pinMode(PIN_RELAY_FAN, OUTPUT);
  
  // Đưa Relay về trạng thái TẮT ban đầu để tránh quạt chạy đột ngột khi vừa cấp nguồn
  if (RELAY_ACTIVE_LOW) {
    digitalWrite(PIN_RELAY_FAN, HIGH); // Mức HIGH tương ứng TẮT với Active LOW
  } else {
    digitalWrite(PIN_RELAY_FAN, LOW);  // Mức LOW tương ứng TẮT với Active HIGH
  }
  
  Serial.println("Trang thai ban dau: Da TAT Relay (Quat khong quay)");
  Serial.println("---------------------------------------------");
  Serial.println("Bat dau chu ky kiem tra: 5 giay BAT / 5 giay TAT...");
}

void loop() {
  // ==================== 1. BẬT RELAY (QUẠT QUAY) ====================
  Serial.println("[RELAY] -> DANG BAT (ON) - Quat se quay...");
  
  if (RELAY_ACTIVE_LOW) {
    digitalWrite(PIN_RELAY_FAN, LOW);  // Kích mức THẤP để BẬT
  } else {
    digitalWrite(PIN_RELAY_FAN, HIGH); // Kích mức CAO để BẬT
  }
  
  // Đợi 5 giây
  delay(5000);
  
  // ==================== 2. TẮT RELAY (QUẠT DỪNG) ====================
  Serial.println("[RELAY] -> DANG TAT (OFF) - Quat se dung...");
  
  if (RELAY_ACTIVE_LOW) {
    digitalWrite(PIN_RELAY_FAN, HIGH); // Kích mức CAO để TẮT
  } else {
    digitalWrite(PIN_RELAY_FAN, LOW);  // Kích mức THẤP để TẮT
  }
  
  // Đợi 5 giây
  delay(5000);
}
