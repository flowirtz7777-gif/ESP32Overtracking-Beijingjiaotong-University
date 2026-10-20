#pragma once
#include <Arduino.h>

class SpeedCan {
public:
  // bitrate: 250000 / 500000 / 1000000
  bool begin(int can_tx_pin, int can_rx_pin, uint32_t bitrate = 500000);
  void poll();   // 非阻塞：读到帧就打印（你还没车速定义，先全收）

  uint32_t rx_count() const { return _rx_cnt; }
  uint32_t err_count() const { return _err_cnt; }

private:
  uint32_t _rx_cnt = 0;
  uint32_t _err_cnt = 0;
  uint32_t _lastStatMs = 0;
};