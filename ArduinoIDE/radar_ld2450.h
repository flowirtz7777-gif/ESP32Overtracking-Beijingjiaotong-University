#pragma once
#include <Arduino.h>

class RadarLD2450 {
public:
  void begin(HardwareSerial& ser, uint32_t baud, int rxPin, int txPin);
  void poll();                 // 尽量频繁调用
  uint32_t bytes_per_sec() const { return _bps; }

private:
  HardwareSerial* _ser = nullptr;
  uint32_t _last_ms = 0;
  uint32_t _cnt = 0;
  uint32_t _bps = 0;
};