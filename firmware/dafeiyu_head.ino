/************************************************************
 * 大肥鱼头壳固件骨架 v0.1（ESP32-S3-DevKitC-1 N16R8）
 *
 * 硬件对照（接到手后按实物改引脚）：
 *   显示 2.8" 圆屏 480×480（ST7796U，SPI）
 *        备选 1.28" GC9A01 240×240 —— 改 SCREEN_W/H 与驱动构造
 *   麦克风 INMP441  → I2S0: SCK=GPIO4  WS=GPIO5  SD=GPIO6
 *   功放 MAX98357A  → I2S1: BCLK=GPIO16 LRC=GPIO17 DIN=GPIO15
 *   舵机 MG90S ×2   → 颈水平=GPIO1  颈俯仰=GPIO2（LEDC 50Hz）
 *   背光            → GPIO13（PWM 可调亮度）
 *
 * 依赖（Arduino Library Manager 安装）：
 *   Arduino_GFX ｜ WebSockets by Markus Sattler ｜ ESP32Servo
 *
 * 工作流（状态机）：
 *   IDLE(待机眨眼) → 唤醒/VAD → LISTEN(录音流上行)
 *   → THINK(思考表情) → SPEAK(播放TTS+表情+动作) → IDLE
 *
 * 服务端协议（JSON over WebSocket 文本帧，v0.1 先跑文字版）：
 *   上行 {"type":"text","data":"你好"}
 *   下行 {"type":"reply","text":"本鲸记下了","emotion":"开心",
 *         "action":"wag_fast","rice_today":3}
 * 语音版（Opus 分片流）为 v0.2，先把文字链路点亮。
 ************************************************************/

#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include <ESP32Servo.h>
#include <Arduino_GFX_Library.h>   // 若用 TFT_eSPI 则替换本行与显示初始化

/* ======== 需要你填的三样 ======== */
const char *WIFI_SSID = "你的WiFi名";
const char *WIFI_PASS = "你的WiFi密码";
const char *SERVER_WS = "ws://192.168.x.x:8765/ws";   // 跑服务端的电脑局域网 IP

/* ======== 显示（按屏幕驱动改） ======== */
#define SCREEN_W 480
#define SCREEN_H 480
// 2.8 寸 ST7796 圆屏常见接线，具体以模块丝印为准：
Arduino_DataBus *bus = new Arduino_ESP32SPI(9 /*DC*/, 10 /*CS*/, 12 /*SCK*/, 11 /*MOSI*/, GFX_NOT_DEFINED /*MISO*/);
Arduino_GFX *gfx = new Arduino_ST7796(bus, 14 /*RST*/, 0 /*rot*/, false /*IPS*/, 480, 480);
#define BL_PIN 13

/* ======== 舵机 ======== */
Servo servoPan, servoTilt;
int panAngle = 90, tiltAngle = 90;

/* ======== WebSocket ======== */
using namespace websockets;
WebsocketsClient wsClient;
bool wsConnected = false;

/* ======== 状态机 ======== */
enum State { IDLE, LISTEN, THINK, SPEAK };
State state = IDLE;
unsigned long tState = 0;
int blinkPhase = 0;

/* ---------- 表情/动作：显示层 v0.1 先画简易脸，v0.2 换精灵图 ---------- */
/* face_round_480.png 转 RGB565 数组后放到 SPIFFS/LittleFS，
   这里留接口：showEmotion(const char* emu) 按 emu 切换贴图 */
void showEmotion(const char *e) {
  // TODO: v0.2 从 LittleFS 取 face_round_480.png / 对应表情帧绘制
  Serial.printf("[FACE] %s\n", e);
}

void doAction(const char *a) {
  if (strcmp(a, "wag_fast") == 0) {           // 开心：快速点头
    for (int i = 0; i < 4; i++) { servoTilt.write(75); delay(90); servoTilt.write(105); delay(90); }
    servoTilt.write(tiltAngle);
  } else if (strcmp(a, "wiggle") == 0) {      // 炸毛：左右摇头
    for (int i = 0; i < 3; i++) { servoPan.write(70); delay(120); servoPan.write(110); delay(120); }
    servoPan.write(panAngle);
  } else if (strcmp(a, "sleep") == 0) {       // 瞌睡：低头
    servoTilt.write(tiltAngle + 25); delay(400); servoTilt.write(tiltAngle);
  }
}

/* ---------- WebSocket ---------- */
void onWsMessage(WebsocketsMessage msg) {
  // v0.1 文本 JSON；v0.2 二进制帧 = TTS 音频流
  Serial.printf("[WS] %s\n", msg.c_str());
  // TODO: ArduinoJson 解析 reply，然后：
  //   showEmotion(emotion); doAction(action); 播放 TTS；屏幕右上角画 rice_today
}

void wsConnect() {
  wsClient.onMessage(onWsMessage);
  wsClient.connect(SERVER_WS) ? (wsConnected = true) : (wsConnected = false);
}

/* ---------- 主循环 ---------- */
void setup() {
  Serial.begin(115200);
  pinMode(BL_PIN, OUTPUT); digitalWrite(BL_PIN, HIGH);

  ESP32PWM::allocateTimer(0); ESP32PWM::allocateTimer(1);
  servoPan.setPeriodHertz(50);  servoTilt.setPeriodHertz(50);
  servoPan.attach(1, 500, 2400); servoTilt.attach(2, 500, 2400);
  servoPan.write(panAngle); servoTilt.write(tiltAngle);

  gfx->begin(); gfx->fillScreen(BLACK);
  showEmotion("idle");

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("[WiFi] connecting");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.printf("\n[WiFi] ok, IP=%s\n", WiFi.localIP().toString().c_str());

  wsConnect();
}

void loop() {
  if (WiFi.status() == WL_CONNECTED && !wsClient.available()) wsConnect();
  wsClient.poll();

  /* 待机动画：每 4s 眨眼（v0.1 只串口打印，v0.2 换帧） */
  static unsigned long tBlink = 0;
  if (state == IDLE && millis() - tBlink > 4000) { tBlink = millis(); showEmotion("blink"); }

  /* TODO(v0.2): INMP441 采样 → VAD → Opus 编码 → wsClient.sendBinary()
     TODO(v0.2): 收到 TTS 二进制帧 → I2S1 播放，同步嘴型/摆尾 */
}
