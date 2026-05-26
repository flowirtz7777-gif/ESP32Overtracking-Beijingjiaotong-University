#pragma once
#include <Arduino.h>

// ======================
// 角度传感器（模拟输入）
// ======================
static constexpr int PIN_ALPHA_ADC = 34;   // AS5600(alpha) OUT -> GPIO34
static constexpr int PIN_PHI_ADC   = 35;   // 牵引角(phi) OUT   -> GPIO35

// ======================
// 报警输出（可选）
// ======================
static constexpr int PIN_BUZZER = 12;
static constexpr int PIN_LED    = 13;

// ======================
// ADC 参数
// ======================
static constexpr float ADC_VREF = 3.3f;
static constexpr int   ADC_MAX  = 4095;

// ======================
// 简单滤波（IIR）
// ======================
static constexpr float LPF_K_ALPHA = 0.12f;  // 0.05~0.2
static constexpr float LPF_K_PHI   = 0.12f;

// ======================
// 标定（先占位：0~4095 -> 0~2pi）
// 你后面会做真实标定（零位、比例、方向）
// ======================
static constexpr float ALPHA_GAIN_RAD_PER_ADC = (2.0f * PI) / ADC_MAX;
static constexpr float ALPHA_OFFSET_RAD       = 0.0f;

static constexpr float PHI_GAIN_RAD_PER_ADC   = (2.0f * PI) / ADC_MAX;
static constexpr float PHI_OFFSET_RAD         = 0.0f;

// ======================
// 雷达 UART（RS485 转回 TTL）
// 重要：Serial2.begin(baud, ..., RX, TX)
// RX=GPIO16（接模块TXD）
// TX=GPIO17（接模块RXD）
// ======================
static constexpr int PIN_RADAR_RX = 16;
static constexpr int PIN_RADAR_TX = 17;
static constexpr uint32_t RADAR_BAUD = 115200;

// ======================
// CAN (TWAI)
// ======================
static constexpr int PIN_CAN_TX = 5;   // ESP32 TX -> CAN收发器 D(TX)
static constexpr int PIN_CAN_RX = 4;   // ESP32 RX <- CAN收发器 R(RX)

// ======================
// 主循环节拍
// ======================
static constexpr uint32_t LOOP_DT_MS = 20;   // 50Hz