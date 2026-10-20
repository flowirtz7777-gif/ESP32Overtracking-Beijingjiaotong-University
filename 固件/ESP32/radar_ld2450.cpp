#include "radar_ld2450.h"

void RadarLD2450::begin(HardwareSerial& ser, uint32_t baud, int rxPin, int txPin) {
  _ser = &ser;
  // 注意：Arduino ESP32 的 begin 参数顺序是 (baud, config, rx, tx)
  _ser->begin(baud, SERIAL_8N1, rxPin, txPin);

  _last_ms = millis();
  _cnt = 0;
  _bps = 0;
}

void RadarLD2450::poll() {
  if(!_ser) return;

  while(_ser->available()) {
    (void)_ser->read();
    _cnt++;
  }

  uint32_t now = millis();
  if(now - _last_ms >= 1000) {
    _bps = _cnt;
    _cnt = 0;
    _last_ms = now;
  }
}