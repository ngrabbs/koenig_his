#define TINY_GSM_MODEM_SIM7600  // Specify modem type

#include <Arduino.h>
#include <TinyGsmClient.h>
#include <ArduinoJson.h>

// Webhook URL
const char server[] = "webhook.site";
//const char resource[] = "/9ce23e1b-6868-4b7e-a6a8-3ed3e389be17";  // Adjust to your Webhook.site URL
const char resource[] = "/telemetry";  // Adjust to your Webhook.site URL

//const char c2_server[] = "10.0.0.2";  // Replace with your PC's IP (not localhost)
const char c2_server[] = "172.16.0.1";  // Replace with your PC's IP (not localhost)
const int c2_port = 8080;
const int c2_server_timeout = 5000;

#define DEBUG

// Modem pins (adjust for your board)

#define BATTERY_ADC_PIN 35
#define ADC_MAX 4095
#define ADC_VREF 3.3  // Default ESP32 ADC reference voltage

#define uS_TO_S_FACTOR      1000000ULL  /* Conversion factor for micro seconds to seconds */
#define TIME_TO_SLEEP       30          /* Time ESP32 will go to sleep (in seconds) */

#define UART_BAUD           115200

#define MODEM_TX            27
#define MODEM_RX            26
#define MODEM_PWRKEY        4
#define MODEM_DTR           32
#define MODEM_RI            33
#define MODEM_FLIGHT        25
#define MODEM_STATUS        34

#define SD_MISO             2
#define SD_MOSI             15
#define SD_SCLK             14
#define SD_CS               14

#define LED_PIN             12

#define CAPTURE_TRIGGER_PIN 5 

#define SerialMon Serial
#define SerialAT Serial1

const char apn[] = "srsapn";
float lat = 0.0, lon = 0.0;
// unsigned long telemetryInterval = 60000;  // Default 60 sec
unsigned long telemetryInterval = 10000;  // Default 60 sec

TinyGsm modem(SerialAT);
TinyGsmClient clientPost(modem);
TinyGsmClient clientGet(modem);

void sendAck(JsonArray cmds) {
  StaticJsonDocument<256> ackDoc;
  ackDoc["acknowledged"] = cmds;

  String ackPayload;
  serializeJson(ackDoc, ackPayload);
  SerialMon.println(ackPayload);

  TinyGsmClient clientAck(modem);
  if (clientAck.connect(c2_server, c2_port, c2_server_timeout)) {
    clientAck.setTimeout(c2_server_timeout);
    clientAck.println("POST /acknowledge HTTP/1.1");
    clientAck.println("Host: " + String(c2_server));
    clientAck.println("Content-Type: application/json");
    clientAck.print("Content-Length: ");
    clientAck.println(ackPayload.length());
    clientAck.println();
    clientAck.println(ackPayload);
  } else {
    SerialMon.println("Failed to connect for ACK");
  }

  clientAck.stop();
}

void triggerCapture() {
  SerialMon.println("Triggering capture GPIO HIGH");
  digitalWrite(CAPTURE_TRIGGER_PIN, HIGH);
  delay(500);  // Adjust as needed
  digitalWrite(CAPTURE_TRIGGER_PIN, LOW);
  SerialMon.println("Capture trigger complete");
}


void fetchCommands() {
  SerialMon.println("Connecting to C2 server...");
  SerialMon.printf("Trying GET to %s:%d\n", c2_server, c2_port);
  if (clientGet.connect(c2_server, c2_port, c2_server_timeout)) {
    SerialMon.println("Connected to C2 server");
    clientGet.setTimeout(c2_server_timeout);
    clientGet.println("GET /commands HTTP/1.1");
    clientGet.println("Host: " + String(c2_server));
    clientGet.println("Connection: close");
    clientGet.println();

    while (clientGet.connected()) {
      String line = clientGet.readStringUntil('\n');
      if (line == "\r") break;  // Headers done

      // Optional: Print headers
    }

    // Read body
    String payload;
    while (clientGet.available()) {
      char c = clientGet.read();
      payload += c;
    }

    SerialMon.println("Received commands:");
    SerialMon.println(payload);



    // Parse commands
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, payload);
    if (!error) {
      JsonArray cmds = doc["commands"];

      // acknowledge receipt of commands to clear command queue
      sendAck(cmds);

      for (JsonObject cmd : cmds) {
        String action = cmd["action"];
        if (action == "set_interval") {
          int newInterval = cmd["value"];
          SerialMon.printf("Setting interval to %d seconds\n", newInterval);
          // Update telemetry interval here (add a global variable)
        } else if (action == "capture_image") {
          SerialMon.println("Triggering image capture...");
          triggerCapture();
        } else if (action == "take_gps_snapshot") {
          SerialMon.println("Taking GPS snapshot...");
          // Add GPS logic here
        } else if (action == "sleep") {
          int sleepTime = cmd["value"];
          SerialMon.printf("Sleeping for %d seconds...\n", sleepTime);
          esp_sleep_enable_timer_wakeup((uint64_t)sleepTime * 1000000ULL);
          esp_deep_sleep_start();
        } else if (action == "reboot") {
          SerialMon.println("Rebooting system...");
          delay(1000);
          ESP.restart();
        }
      }
    } else {
      SerialMon.println("Failed to parse commands");
    }

  } else {
    SerialMon.println("Failed to connect to C2 server");
  }

  clientGet.stop();
}


String getOperatorInfo() {
  modem.sendAT("+COPS?");
  if (modem.waitResponse(1000, "+COPS:") == 1) {
    String line = modem.stream.readStringUntil('\n');
    return line;  // Example: +COPS: 0,2,"00101",7
  }
  return "No operator info";
}

String getLteStatus() {
  modem.sendAT("+CPSI?");
  if (modem.waitResponse(1000, "+CPSI:") == 1) {
    String line = modem.stream.readStringUntil('\n');
    return line;  // Example: +CPSI: LTE,Online,310-410,0x1234,earfcn,band,rsrp,rsrq
  }
  return "No LTE status";
}

void enableLteMetrics() {
  modem.sendAT("+QENG=\"servingcell\",2");  // Mode 2: Enable extended metrics
  modem.waitResponse();
}

String getLteMetrics() {
  modem.sendAT("+QENG=\"servingcell\"");
  if (modem.waitResponse(1000, "+QENG:") == 1) {
    String line = modem.stream.readStringUntil('\n');
    return line;  // Raw output
  }
  return "";
}


float readBatteryVoltage() {
  int raw = analogRead(BATTERY_ADC_PIN);
  float voltage = (raw / (float)ADC_MAX) * ADC_VREF;
  // Adjust this scaling factor based on your divider
  float batteryVoltage = voltage * 2.0;  // Assuming a 2:1 divider
  return batteryVoltage;
}

void postTelemetry() {
  float battery = readBatteryVoltage();
  int16_t rssi = modem.getSignalQuality();
  String lteMetrics = getLteMetrics();
  if (lteMetrics.length() == 0) {
    lteMetrics = "No LTE metrics";  // Safe fallback
  }

  String lteStatus = getLteStatus();
  if (lteStatus.length() == 0) {
    lteStatus = "No LTE status";  // Safe fallback
  }
  String lteOperatorInfo = getOperatorInfo();
  if (lteOperatorInfo.length() == 0) {
    lteOperatorInfo = "No LTE operator info";  // Safe fallback
  } 
  float lat = 0.0, lon = 0.0;
  modem.getGPS(&lat, &lon);
  
  // Build JSON payload
  StaticJsonDocument<512> doc;
  doc["battery"] = battery;
  doc["rssi"] = rssi;
  doc["lte"] = lteMetrics;
//  doc["lteStatus"] = lteStatus;
//  doc["opInfo"] = lteOperatorInfo;
  doc["lat"] = lat;
  doc["lon"] = lon;


  String json;
  serializeJson(doc, json);
  SerialMon.println("Telemetry JSON:");
  SerialMon.println(json);

  // POST the data (same as before)
  if (clientPost.connect(c2_server, c2_port, c2_server_timeout)) {
    clientPost.setTimeout(c2_server_timeout);
    clientPost.println("POST " + String(resource) + " HTTP/1.1");
    clientPost.println("Host: " + String(server));
    clientPost.println("Content-Type: application/json");
    clientPost.print("Content-Length: ");
    clientPost.println(json.length());
    clientPost.println();
    clientPost.println(json);
  } else {
    SerialMon.println("Failed to connect to server");
  }

  clientPost.stop();
}



void setup() {
  SerialMon.begin(115200);
  delay(10);


  SerialAT.begin(115200, SERIAL_8N1, MODEM_RX, MODEM_TX);

  // Power on modem
  pinMode(MODEM_PWRKEY, OUTPUT);
  digitalWrite(MODEM_PWRKEY, HIGH);
  delay(1000);
  digitalWrite(MODEM_PWRKEY, LOW);
  delay(10000);  // Give time for the modem to boot

  SerialMon.println("Initializing modem...");
  modem.restart();

  SerialMon.println("Waiting for network...");
  if (!modem.waitForNetwork()) {
    SerialMon.println("Network not found...");
    while (true);
  }

  SerialMon.println("Connecting to APN...");
  if (!modem.gprsConnect(apn)) {
    SerialMon.println("GPRS connect failed...");
    while (true);
  }

  SerialMon.println("Connected!");

  // capture pin to trigger pi's to capture image
  pinMode(CAPTURE_TRIGGER_PIN, OUTPUT);
  digitalWrite(CAPTURE_TRIGGER_PIN, LOW);

  modem.enableGPS();
  enableLteMetrics();

}

void loop() {
  postTelemetry();
  delay(telemetryInterval);  // Placeholder for now

  fetchCommands();
  delay(telemetryInterval);  // Placeholder for now
}
