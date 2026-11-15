/*
 * 大肥鱼 · 会看人的头 —— 舵机固件 v1.0
 * 板子：Arduino Nano（CH340 版）
 * 舵机：SG90 接 D9
 *
 * 协议：串口 115200，收到 "角度\n" 就转过去，角度范围 0–180
 *       例：90\n  就是回正
 *
 * 烧录：用 Arduino IDE 打开本文件 → 工具选 Arduino Nano / ATmega328P (Old Bootloader) → 上传
 */

#include <Servo.h>

const int SERVO_PIN = 9;
const int MIN_ANGLE = 20;    // 机械限位，防止撞到底
const int MAX_ANGLE = 160;

Servo head;
int lastAngle = 90;
unsigned long lastCmd = 0;

void setup() {
  Serial.begin(115200);
  head.attach(SERVO_PIN);
  head.write(90);            // 上电回正
  delay(400);
}

void loop() {
  // 读串口，一行一个角度
  if (Serial.available() > 0) {
    int a = Serial.parseInt();          // 自动跳过 \r \n
    if (Serial.peek() == '\n' || Serial.peek() == '\r') Serial.read();

    if (a >= 0 && a <= 180) {
      a = constrain(a, MIN_ANGLE, MAX_ANGLE);

      // 限速：一次最多动 12 度，防止"啪"一下甩过去
      int delta = a - lastAngle;
      if (delta > 12)  a = lastAngle + 12;
      if (delta < -12) a = lastAngle - 12;

      head.write(a);
      lastAngle = a;
      lastCmd = millis();
      Serial.print("OK ");              // 回执，浏览器可以读
      Serial.println(a);
    } else if (a != 0) {
      Serial.print("ERR ");
      Serial.println(a);
    }
  }

  // 5 秒没收到指令就慢慢回正（像"没人在，就看前面"）
  if (millis() - lastCmd > 5000 && lastAngle != 90) {
    if (lastAngle > 90) lastAngle--;
    else lastAngle++;
    head.write(lastAngle);
    delay(30);
  }
}
