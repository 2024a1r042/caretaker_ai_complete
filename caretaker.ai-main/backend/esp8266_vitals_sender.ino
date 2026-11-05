// ============================================================
//  ESP8266 → FastAPI Vitals Sender
//  Board  : NodeMCU / Wemos D1 Mini (ESP8266)
//  Sensors: MAX30102 (Heart Rate + SpO2)
//           MLX90614 (Non-contact temperature)
//
//  Arduino IDE Libraries needed (install via Library Manager):
//  1. ESP8266WiFi        → comes with ESP8266 board package
//  2. ESP8266HTTPClient  → comes with ESP8266 board package
//  3. ArduinoJson        → search "ArduinoJson" by Benoit Blanchon  (v6.x)
//  4. MAX30105           → search "SparkFun MAX3010x"
//  5. MLX90614           → search "Adafruit MLX90614"
//  6. Wire               → built-in (for I2C)
//
//  Board Manager URL (paste in Arduino IDE → Preferences):
//  http://arduino.esp8266.com/stable/package_esp8266com_index.json
// ============================================================

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include "MAX30105.h"      // SparkFun MAX3010x library
#include "spo2_algorithm.h"
#include <Adafruit_MLX90614.h>

// ── WiFi credentials ───────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_NAME";     // <-- change
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"; // <-- change

// ── Backend settings ───────────────────────────────────────
// Replace with your PC's local IP (run `ipconfig` to find it)
const char* SERVER_IP   = "192.168.1.100";   // <-- change to your PC IP
const int   SERVER_PORT = 8000;
const int   CARE_RECIPIENT_ID = 1;            // <-- which elder's record

// Must match ESP_SECRET_KEY in routes/vitals.py
const char* SECRET_KEY  = "caretaker_esp_2024";

// How often to send data (milliseconds)
const unsigned long SEND_INTERVAL_MS = 30000; // every 30 seconds

// ── Sensor objects ─────────────────────────────────────────
MAX30105 particleSensor;
Adafruit_MLX90614 mlx;

// ── MAX30102 buffers ───────────────────────────────────────
const byte SAMPLE_LENGTH = 100;
uint32_t irBuffer[SAMPLE_LENGTH];
uint32_t redBuffer[SAMPLE_LENGTH];
int32_t  spo2Value;
int8_t   spo2Valid;
int32_t  heartRateValue;
int8_t   hrValid;

// ── Timing ─────────────────────────────────────────────────
unsigned long lastSendTime = 0;

// ───────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Wire.begin();   // SDA=D2, SCL=D1 on NodeMCU by default

  // ── MAX30102 init ──────────────────────────────────────
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("❌ MAX30102 not found. Check wiring!");
    while (true); // halt
  }
  particleSensor.setup();
  particleSensor.setPulseAmplitudeRed(0x0A);
  particleSensor.setPulseAmplitudeGreen(0);
  Serial.println("✅ MAX30102 ready");

  // ── MLX90614 init ─────────────────────────────────────
  if (!mlx.begin()) {
    Serial.println("❌ MLX90614 not found. Check wiring!");
    // Non-fatal: we'll just skip temperature
  } else {
    Serial.println("✅ MLX90614 ready");
  }

  // ── WiFi ──────────────────────────────────────────────
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("✅ WiFi connected. IP: ");
  Serial.println(WiFi.localIP());
}

// ───────────────────────────────────────────────────────────
void readMAX30102() {
  // Collect SAMPLE_LENGTH samples first
  for (byte i = 0; i < SAMPLE_LENGTH; i++) {
    while (!particleSensor.available())
      particleSensor.check();

    redBuffer[i] = particleSensor.getRed();
    irBuffer[i]  = particleSensor.getIR();
    particleSensor.nextSample();
  }
  // Run the SparkFun algorithm
  maxim_heart_rate_and_oxygen_saturation(
    irBuffer, SAMPLE_LENGTH, redBuffer,
    &spo2Value, &spo2Valid,
    &heartRateValue, &hrValid
  );
}

// ───────────────────────────────────────────────────────────
void sendToBackend(int heartRate, int spo2, float tempC) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi disconnected, skipping send");
    return;
  }

  WiFiClient client;
  HTTPClient http;

  String url = "http://" + String(SERVER_IP) + ":" + String(SERVER_PORT) + "/api/vitals/record";
  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");

  // Build JSON payload
  StaticJsonDocument<256> doc;
  doc["care_recipient_id"] = CARE_RECIPIENT_ID;
  doc["secret_key"]        = SECRET_KEY;

  if (heartRate > 0 && heartRate < 300)
    doc["heart_rate"] = heartRate;

  if (spo2 > 70 && spo2 <= 100)
    doc["oxygen_saturation"] = spo2;

  if (tempC > 25.0 && tempC < 45.0)
    doc["temperature"] = tempC;

  String body;
  serializeJson(doc, body);

  Serial.println("📤 Sending: " + body);

  int httpCode = http.POST(body);
  if (httpCode == 200) {
    Serial.println("✅ Server accepted: " + http.getString());
  } else {
    Serial.println("❌ HTTP error: " + String(httpCode));
    Serial.println(http.getString());
  }

  http.end();
}

// ───────────────────────────────────────────────────────────
void loop() {
  unsigned long now = millis();
  if (now - lastSendTime < SEND_INTERVAL_MS) return;
  lastSendTime = now;

  // 1. Read MAX30102
  readMAX30102();
  int hr   = hrValid   ? (int)heartRateValue : -1;
  int spo2 = spo2Valid ? (int)spo2Value      : -1;
  Serial.printf("Heart Rate: %d bpm | SpO2: %d %%\n", hr, spo2);

  // 2. Read temperature
  float tempC = mlx.readObjectTempC();
  Serial.printf("Temperature: %.1f °C\n", tempC);

  // 3. POST to FastAPI
  sendToBackend(hr, spo2, tempC);
}
