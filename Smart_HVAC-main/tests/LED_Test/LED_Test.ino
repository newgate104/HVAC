/**
 * LED_Test.ino
 * 
 * Chương trình kiểm tra hoạt động của các hệ thống đèn LED chỉ thị nhiệt độ trên ESP32-S3.
 * Hỗ trợ đồng thời 2 phương án hiển thị:
 * 
 * PƯƠNG ÁN A: Sử dụng đèn LED RGB WS2812B tích hợp sẵn trên mạch ESP32-S3 (chân GPIO48)
 *   - Sáng màu XANH DƯƠNG (Cooling) trong 2 giây.
 *   - Sáng màu ĐỎ (Heating) trong 2 giây.
 * 
 * PHƯƠNG ÁN B: Sử dụng 2 bóng đèn LED rời đấu nối ngoài
 *   - LED Xanh dương (Cooling) nối chân GPIO10 -> Sáng trong 2 giây.
 *   - LED Đỏ (Heating) nối chân GPIO11 -> Sáng trong 2 giây.
 */

// =========================================================================
// ⚙️ CẤU HÌNH CHÂN KẾT NỐI
// =========================================================================

// 1. Cấu hình LED RGB WS2812B tích hợp sẵn trên mạch
#define PIN_RGB_ONBOARD   48    // Chân điều khiển LED RGB onboard mặc định của ESP32-S3

// 2. Cấu hình chân cho 2 đèn LED rời đấu nối ngoài (nếu có dùng)
#define PIN_LED_COOLING   10    // LED rời báo làm mát (nối chân GPIO10)
#define PIN_LED_HEATING   11    // LED rời báo làm ấm (nối chân GPIO11)

void setup() {
  // Khởi tạo Serial Monitor
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n=============================================");
  Serial.println("   KHOI TONG KIEM TRA HE THONG DEN LED");
  Serial.println("=============================================");
  
  // Khởi tạo chân GPIO cho 2 LED rời ngoài làm OUTPUT
  pinMode(PIN_LED_COOLING, OUTPUT);
  pinMode(PIN_LED_HEATING, OUTPUT);
  
  // Đưa tất cả về trạng thái tắt ban đầu
  digitalWrite(PIN_LED_COOLING, LOW);
  digitalWrite(PIN_LED_HEATING, LOW);
  
  // Đối với LED RGB onboard sử dụng hàm neopixelWrite (tích hợp sẵn trong core ESP32, không cần thư viện)
  // Tắt đèn RGB onboard ban đầu (RGB = 0, 0, 0)
  neopixelWrite(PIN_RGB_ONBOARD, 0, 0, 0); 
  
  Serial.println("Chu ky kiem tra: 2 giay XANH (Làm mát) / 2 giay ĐỎ (Làm ấm)...");
  Serial.println("---------------------------------------------");
}

void loop() {
  // ==================== TRẠNG THÁI 1: LÀM MÁT (COOLING) ====================
  Serial.println("[LED] -> Đang bật trạng thái LÀM MÁT (XANH DƯƠNG)...");
  
  // 1. Bật màu Xanh Dương (Blue) trên LED RGB onboard: R=0, G=0, B=64 (độ sáng vừa phải)
  neopixelWrite(PIN_RGB_ONBOARD, 0, 0, 64);
  
  // 2. Điều khiển LED ngoài: Bật LED Xanh (GPIO10), Tắt LED Đỏ (GPIO11)
  digitalWrite(PIN_LED_COOLING, HIGH);
  digitalWrite(PIN_LED_HEATING, LOW);
  
  delay(2000); // Giữ trạng thái trong 2 giây

  // ==================== TRẠNG THÁI 2: LÀM ẤM (HEATING) ====================
  Serial.println("[LED] -> Đang bật trạng thái LÀM ẤM (ĐỎ)...");
  
  // 1. Bật màu Đỏ (Red) trên LED RGB onboard: R=64, G=0, B=0
  neopixelWrite(PIN_RGB_ONBOARD, 64, 0, 0);
  
  // 2. Điều khiển LED ngoài: Tắt LED Xanh (GPIO10), Bật LED Đỏ (GPIO11)
  digitalWrite(PIN_LED_COOLING, LOW);
  digitalWrite(PIN_LED_HEATING, HIGH);
  
  delay(2000); // Giữ trạng thái trong 2 giây
}
