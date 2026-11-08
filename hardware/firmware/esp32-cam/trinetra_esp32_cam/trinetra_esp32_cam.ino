/**
 * ============================================================================
 * TRINETRA (त्रिनेत्र) — ESP32-CAM MJPEG Streaming Firmware
 * ============================================================================
 * Target Hardware: AI-Thinker ESP32-CAM (RHYX M21-45 / GC2145 / OV2640 with external PSRAM)
 * Purpose: Streams low-latency video to Trinetra Vision Engine over WiFi
 *
 * Supported Modes:
 *   1. Station Mode: Connects to your laptop/phone hotspot or home WiFi
 *   2. SoftAP Mode: ESP32 broadcasts its own WiFi network ("Trinetra-Cam")
 *
 * Endpoints:
 *   - http://<ip>:81/stream  -> Low-latency MJPEG video stream (OpenCV compatible)
 *   - http://<ip>/status     -> JSON health, uptime, WiFi RSSI, and free heap
 *   - http://<ip>/capture    -> Single full-resolution snapshot (JPEG)
 * ============================================================================
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_timer.h"
#include "img_converters.h"
#include "fb_gfx.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "esp_http_server.h"

// ============================================================================
// 1. WiFi Configuration
// ============================================================================
// Set to 1 to connect to an existing WiFi/Hotspot; 0 to create "Trinetra-Cam" AP
#define USE_STATION_MODE 1

#if USE_STATION_MODE
  const char* ssid     = "A21";
  const char* password = "ANDROID27@26";
#else
  const char* ap_ssid  = "Trinetra-ChestCam";
  const char* ap_pass  = "trinetra123";  // Min 8 chars
#endif

// ============================================================================
// 2. Camera Hardware Pinout (AI-Thinker ESP32-CAM)
// ============================================================================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define FLASH_LED_PIN      4

// ============================================================================
// 3. HTTP MJPEG Stream Constants
// ============================================================================
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t stream_httpd = NULL;
httpd_handle_t camera_httpd = NULL;

// Stream handler for port 81 (/stream)
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t * fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t * _jpg_buf = NULL;
  char * part_buf[64];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) {
    return res;
  }

  // Set permissive CORS so web clients and Python can access the stream
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[Camera] Frame capture failed");
      res = ESP_FAIL;
    } else {
      // If sensor does not output JPEG directly (e.g. OV7670 / RGB565 / YUV422),
      // convert frame to JPEG on the fly
      if (fb->format != PIXFORMAT_JPEG) {
        bool converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
        esp_camera_fb_return(fb);
        fb = NULL;
        if (!converted) {
          Serial.println("[Camera] Software JPEG conversion failed");
          res = ESP_FAIL;
        }
      } else {
        _jpg_buf_len = fb->len;
        _jpg_buf = fb->buf;
      }
    }

    if (res == ESP_OK) {
      size_t hlen = snprintf((char *)part_buf, 64, _STREAM_PART, _jpg_buf_len);
      res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    }

    if (fb) {
      esp_camera_fb_return(fb);
      fb = NULL;
      _jpg_buf = NULL;
    } else if (_jpg_buf) {
      free(_jpg_buf);
      _jpg_buf = NULL;
    }

    if (res != ESP_OK) {
      break;
    }
  }

  return res;
}

// Status handler for port 80 (/status)
static esp_err_t status_handler(httpd_req_t *req) {
  char json_response[256];
  snprintf(json_response, sizeof(json_response),
    "{\"status\":\"online\",\"uptime_ms\":%lu,\"free_heap\":%u,\"rssi\":%d,\"psram\":%s}",
    millis(),
    ESP.getFreeHeap(),
    WiFi.RSSI(),
    psramFound() ? "true" : "false"
  );
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, json_response, strlen(json_response));
}

// Single capture handler for port 80 (/capture)
static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }

  uint8_t * jpg_buf = NULL;
  size_t jpg_buf_len = 0;
  bool converted_alloc = false;

  if (fb->format != PIXFORMAT_JPEG) {
    bool converted = frame2jpg(fb, 80, &jpg_buf, &jpg_buf_len);
    esp_camera_fb_return(fb);
    fb = NULL;
    if (!converted) {
      httpd_resp_send_500(req);
      return ESP_FAIL;
    }
    converted_alloc = true;
  } else {
    jpg_buf = fb->buf;
    jpg_buf_len = fb->len;
  }

  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  esp_err_t res = httpd_resp_send(req, (const char *)jpg_buf, jpg_buf_len);

  if (converted_alloc && jpg_buf) {
    free(jpg_buf);
  } else if (fb) {
    esp_camera_fb_return(fb);
  }
  return res;
}

void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;

  // Main HTTP server (Port 80)
  httpd_uri_t status_uri = {
    .uri       = "/status",
    .method    = HTTP_GET,
    .handler   = status_handler,
    .user_ctx  = NULL
  };
  httpd_uri_t capture_uri = {
    .uri       = "/capture",
    .method    = HTTP_GET,
    .handler   = capture_handler,
    .user_ctx  = NULL
  };

  if (httpd_start(&camera_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &status_uri);
    httpd_register_uri_handler(camera_httpd, &capture_uri);
  }

  // Dedicated Video Streaming server (Port 81)
  config.server_port = 81;
  config.ctrl_port = 32769;
  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };

  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
  }
}

// ============================================================================
// 4. Setup & Main Loop
// ============================================================================
void setup() {
  // Disable brownout detector to prevent sudden Wi-Fi power drops from resetting board
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();
  Serial.println("==========================================");
  Serial.println("   TRINETRA (त्रिनेत्र) ESP32-CAM Rig    ");
  Serial.println("==========================================");

  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW); // Flash OFF

  // Camera Configuration
  // Note: RHYX M21-45 uses GalaxyCore GC2145 sensor (no hardware JPEG, requires 10MHz XCLK)
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;

  // 10MHz XCLK is required for RHYX M21-45 / GC2145 (20MHz causes 0x105 probe failure)
  config.xclk_freq_hz = 10000000;
  config.pixel_format = PIXFORMAT_RGB565; // Native for GC2145 (converted to JPEG dynamically)
  // Use VGA (640x480) for full wide sensor Field of View (QVGA center-crops and looks 2x zoomed in)
  config.frame_size   = psramFound() ? FRAMESIZE_VGA : FRAMESIZE_HVGA;
  config.jpeg_quality = 12;
  config.fb_count     = psramFound() ? 2 : 1;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  Serial.println("[Init] Configuring camera for RHYX M21-45 (GC2145) @ 10MHz RGB565...");

  // Initialize camera sensor
  esp_err_t err = esp_camera_init(&config);
  
  if (err != ESP_OK) {
    Serial.printf("[Init] RGB565 init failed (error 0x%x). Retrying in YUV422 mode...\n", err);
    esp_camera_deinit();
    delay(100);

    config.pixel_format = PIXFORMAT_YUV422;
    err = esp_camera_init(&config);
  }

  // If still failing, try 20MHz JPEG in case an OV2640 is plugged in
  if (err != ESP_OK) {
    Serial.printf("[Init] Non-JPEG modes failed (0x%x). Trying OV2640 20MHz JPEG mode...\n", err);
    esp_camera_deinit();
    delay(100);

    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size   = psramFound() ? FRAMESIZE_VGA : FRAMESIZE_QVGA;
    err = esp_camera_init(&config);
  }

  if (err != ESP_OK) {
    Serial.printf("[Init] FATAL: Camera initialization failed with error 0x%x\n", err);
    Serial.println("[Init] -> Check ribbon cable seating, latch lock, and 5V power supply.");
    return;
  }

  Serial.println("[Init] Camera initialized successfully!");

  // Adjust camera sensor properties for assistive vision
  sensor_t * s = esp_camera_sensor_get();
  if (s != NULL) {
    if (s->id.PID == OV2640_PID || s->id.PID == OV3660_PID || s->id.PID == OV5640_PID) {
      s->set_brightness(s, 1);    // Slightly boost brightness for indoor corridors
      s->set_contrast(s, 1);      // Boost contrast for edge detection
      s->set_saturation(s, 0);
      s->set_whitebal(s, 1);      // Auto white balance
      s->set_awb_gain(s, 1);
    }
  }

  // Initialize Wi-Fi
#if USE_STATION_MODE
  Serial.printf("[WiFi] Connecting to %s...\n", ssid);
  WiFi.begin(ssid, password);
  WiFi.setSleep(false); // Disable WiFi power saving for ultra-low streaming latency

  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 25) {
    delay(500);
    Serial.print(".");
    retry++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected successfully!");
    Serial.print("[WiFi] IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Station failed to connect! Switching to SoftAP fallback...");
    WiFi.disconnect();
    WiFi.softAP("Trinetra-ChestCam", "trinetra123");
    Serial.print("[WiFi] SoftAP IP Address: ");
    Serial.println(WiFi.softAPIP());
  }
#else
  Serial.println("[WiFi] Starting SoftAP 'Trinetra-ChestCam'...");
  WiFi.softAP(ap_ssid, ap_pass);
  Serial.print("[WiFi] SoftAP IP Address: ");
  Serial.println(WiFi.softAPIP());
#endif

  // Start HTTP Servers
  startCameraServer();

  Serial.println("==========================================");
  Serial.println(">>> Trinetra Camera Stream is LIVE <<<");
  Serial.println("Enter this URL into Trinetra Desktop App:");
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("  http://%s:81/stream\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.printf("  http://%s:81/stream\n", WiFi.softAPIP().toString().c_str());
  }
  Serial.println("==========================================");
}

void loop() {
  // Everything is handled asynchronously in FreeRTOS tasks
  delay(1000);
}
