#include "config.h"
#include "sensors_alpha.h"
#include "sensors_phi.h"
#include "radar_ld2450.h"
#include "speed_can.h"
#include "alarm_out.h"

AlphaSensor alphaSensor;
PhiSensor   phiSensor;
RadarLD2450 radar;
SpeedCan    canbus;
AlarmOut    alarm;

uint32_t last_loop_ms = 0;

void setup() {
  Serial.begin(115200);
  delay(300);

  Serial.println("\n=== ICC Warning System (ESP32-S3-N16R8) Phase1+CAN ===");
  Serial.printf("Pins: alpha=%d phi=%d radarRX=%d radarTX=%d canTX=%d canRX=%d\n",
                PIN_ALPHA_ADC, PIN_PHI_ADC, PIN_RADAR_RX, PIN_RADAR_TX, PIN_CAN_TX, PIN_CAN_RX);

  // 1) 角度传感器
  alphaSensor.begin(PIN_ALPHA_ADC);
  phiSensor.begin(PIN_PHI_ADC);

  // 2) 雷达串口（先只统计字节流）
  radar.begin(Serial2, RADAR_BAUD, PIN_RADAR_RX, PIN_RADAR_TX);

  // 3) CAN (TWAI) 全收打印
  bool ok = canbus.begin(PIN_CAN_TX, PIN_CAN_RX, 500000); // 默认500k，若车上是250k再改
  if(!ok) Serial.println("[CAN] init failed!");

  // 4) 报警输出（先不触发）
  alarm.begin(PIN_BUZZER, PIN_LED);

  Serial.println("Setup done.");
}

void loop() {
  // 雷达和CAN尽量勤快轮询
  radar.poll();
  canbus.poll();

  // 50Hz 主循环节拍（用于打印慢速状态）
  uint32_t now = millis();
  if(now - last_loop_ms < LOOP_DT_MS) return;
  last_loop_ms = now;

  float alpha = alphaSensor.read_rad();
  float phi   = phiSensor.read_rad();

  bool danger = false; // 现在还没上预测与危险判定
  alarm.update(danger);

  // 状态打印（慢速）
  Serial.print("[SENS] alpha(rad)="); Serial.print(alpha, 4);
  Serial.print(" phi(rad)=");         Serial.print(phi, 4);
  Serial.print(" adcA=");             Serial.print(alphaSensor.raw_adc());
  Serial.print(" adcP=");             Serial.print(phiSensor.raw_adc());
  Serial.print(" radarBps=");         Serial.print(radar.bytes_per_sec());
  Serial.print(" canRx=");            Serial.print(canbus.rx_count());
  Serial.println();
}