// -----------------------------------------------------------------------------
//  Balloon flight-controller – tidy version
//  Hardware: ESP32 + SIM7600 (TTGO T-SIM7600 / LilyGO T-SIM7600)
// -----------------------------------------------------------------------------
#define TINY_GSM_MODEM_SIM7600
#include <Arduino.h>
#include <TinyGsmClient.h>
#include <ArduinoJson.h>

// ---------- compile-time constants ----------
constexpr uint32_t   UART_BAUD         = 115200;
constexpr uint32_t   CONNECT_TIMEOUT   = 10000;      // ms, our own logic
constexpr uint32_t   SOCKET_TIMEOUT    = 5000;       // ms, for client.setTimeout
constexpr uint32_t   DEFAULT_INTERVAL  = 10000;      // ms, updated by C2

constexpr char       APN[]             = "srsapn";
constexpr char       C2_HOST[]         = "172.16.0.1";
constexpr uint16_t   C2_PORT           = 8080;
constexpr char       TELEMETRY_PATH[]  = "/telemetry";
constexpr char       COMMAND_PATH[]    = "/commands";
constexpr char       ACK_PATH[]        = "/acknowledge";

// pins
constexpr gpio_num_t MODEM_TX          = GPIO_NUM_27;
constexpr gpio_num_t MODEM_RX          = GPIO_NUM_26;
constexpr gpio_num_t MODEM_PWRKEY      = GPIO_NUM_4;

constexpr gpio_num_t CAPTURE_TRIGGER   = GPIO_NUM_5;
constexpr gpio_num_t LED_PIN           = GPIO_NUM_12;

// SD pins – fixed clash removed
constexpr gpio_num_t SD_MISO           = GPIO_NUM_2;
constexpr gpio_num_t SD_MOSI           = GPIO_NUM_15;
constexpr gpio_num_t SD_SCLK           = GPIO_NUM_14;
constexpr gpio_num_t SD_CS             = GPIO_NUM_13;   // <- moved

// battery sense
constexpr gpio_num_t BATTERY_ADC_PIN   = GPIO_NUM_35;
constexpr float      ADC_VREF          = 1.10;       // use the calibrated eFuse reference
constexpr float      VOLTAGE_DIVIDER   = 2.0f;       // 2 : 1 divider

// ---------- globals ----------
TinyGsm        modem(Serial1);
TinyGsmClient  net(modem);            // single reusable socket
uint32_t       telemetryInterval = DEFAULT_INTERVAL;
uint32_t       lastTelemetryMs   = 0;

// ---------- helpers ----------
static bool httpPost(const char* path, const String& body);
static bool httpGet(const char* path, String& out);

// ---------- setup ----------
void setup()
{
    Serial.begin(115200);
    Serial1.begin(UART_BAUD, SERIAL_8N1, MODEM_RX, MODEM_TX);

    pinMode(MODEM_PWRKEY, OUTPUT);
    digitalWrite(MODEM_PWRKEY, HIGH);
    delay(1000);
    digitalWrite(MODEM_PWRKEY, LOW);

    pinMode(CAPTURE_TRIGGER, OUTPUT);
    digitalWrite(CAPTURE_TRIGGER, LOW);
    pinMode(LED_PIN, OUTPUT);

    // Bring up modem
    if (!modem.restart())  ESP.restart();
    if (!modem.waitForNetwork()) ESP.restart();
    if (!modem.gprsConnect(APN)) ESP.restart();

    modem.enableGPS();
    modem.sendAT("+QENG=\"servingcell\",2");   // enable extended metrics
    modem.waitResponse();
}

// ---------- main loop ----------
void loop()
{
    const uint32_t now = millis();

    // time-slice tasks ---------------------------------------------------------
    if (now - lastTelemetryMs >= telemetryInterval)
    {
        lastTelemetryMs = now;
        postTelemetry();
        fetchAndProcessCommands();
    }

    // light-sleep between slices (saves ~20 mA)
    esp_sleep_enable_timer_wakeup(5 * 1000000ULL);   // wake in 5 s max
    esp_light_sleep_start();
}

// -----------------------------------------------------------------------------
//  I/O functions
// -----------------------------------------------------------------------------
static void triggerCapture()
{
    digitalWrite(CAPTURE_TRIGGER, HIGH);
    delay(250);
    digitalWrite(CAPTURE_TRIGGER, LOW);
}

// read Li-ion voltage (assumes ESP32-S2/-S3 ADC calibration in eFuse)
static float readBatteryVoltage()
{
    uint16_t raw = analogRead(BATTERY_ADC_PIN);
    float    v   = (raw / 4095.0f) * ADC_VREF * VOLTAGE_DIVIDER;
    return v;
}

static void postTelemetry()
{
    float  batt  = readBatteryVoltage();
    int16_t rssi = modem.getSignalQuality();
    float  lat   = 0, lon = 0;
    modem.getGPS(&lat, &lon);

    StaticJsonDocument<384> doc;
    doc["batt"] = batt;
    doc["rssi"] = rssi;
    doc["lat"]  = lat;
    doc["lon"]  = lon;

    String body;
    serializeJson(doc, body);

    httpPost(TELEMETRY_PATH, body);
}

static void fetchAndProcessCommands()
{
    String payload;
    if (!httpGet(COMMAND_PATH, payload)) return;

    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, payload)) return;

    JsonArray cmds = doc["commands"].as<JsonArray>();

    // ACK the batch first
    StaticJsonDocument<256> ack;
    ack["acknowledged"] = cmds;
    String ackBody;
    serializeJson(ack, ackBody);
    httpPost(ACK_PATH, ackBody);

    for (JsonObject cmd : cmds)
    {
        const char* action = cmd["action"];
        if (!action) continue;

        if (!strcmp(action, "set_interval"))
        {
            telemetryInterval = cmd["value"] | DEFAULT_INTERVAL;
        }
        else if (!strcmp(action, "capture_image"))
        {
            triggerCapture();
        }
        else if (!strcmp(action, "sleep"))
        {
            uint32_t secs = cmd["value"] | 0;
            esp_sleep_enable_timer_wakeup(secs * 1000000ULL);
            esp_deep_sleep_start();
        }
        else if (!strcmp(action, "reboot"))
        {
            ESP.restart();
        }
    }
}

// -----------------------------------------------------------------------------
//  Minimal HTTP helpers (blocking but bounded by SOCKET_TIMEOUT)
// -----------------------------------------------------------------------------
static bool connectSocket()
{
    if (net.connected()) return true;

    uint32_t start = millis();
    while (!net.connect(C2_HOST, C2_PORT))
    {
        if (millis() - start > CONNECT_TIMEOUT) return false;
    }
    net.setTimeout(SOCKET_TIMEOUT);
    return true;
}

static bool httpPost(const char* path, const String& body)
{
    if (!connectSocket()) return false;

    net.printf("POST %s HTTP/1.1\r\n", path);
    net.printf("Host: %s\r\n", C2_HOST);
    net.println(F("Content-Type: application/json"));
    net.printf("Content-Length: %u\r\n\r\n", body.length());
    net.print(body);

    // Skip response headers quickly
    String line = net.readStringUntil('\n');
    return line.startsWith("HTTP/1.1 2");
}

static bool httpGet(const char* path, String& out)
{
    if (!connectSocket()) return false;

    net.printf("GET %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n",
               path, C2_HOST);

    if (!net.find("\r\n\r\n")) return false;    // skip headers

    out.reserve(512);
    uint32_t deadline = millis() + SOCKET_TIMEOUT;
    while (net.connected() && millis() < deadline)
    {
        while (net.available()) out += (char)net.read();
    }
    net.stop();
    return true;
}

