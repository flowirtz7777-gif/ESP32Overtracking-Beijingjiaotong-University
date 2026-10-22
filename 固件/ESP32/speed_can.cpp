#include "speed_can.h"

extern "C" {
  #include "driver/twai.h"
}

bool SpeedCan::begin(int can_tx_pin, int can_rx_pin, uint32_t bitrate) {
  twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT(
      (gpio_num_t)can_tx_pin,
      (gpio_num_t)can_rx_pin,
      TWAI_MODE_NORMAL
  );

  twai_timing_config_t t_config;
  if (bitrate == 250000)       t_config = TWAI_TIMING_CONFIG_250KBITS();
  else if (bitrate == 500000)  t_config = TWAI_TIMING_CONFIG_500KBITS();
  else if (bitrate == 1000000) t_config = TWAI_TIMING_CONFIG_1MBITS();
  else                         t_config = TWAI_TIMING_CONFIG_500KBITS();

  twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

  esp_err_t err = twai_driver_install(&g_config, &t_config, &f_config);
  if (err != ESP_OK) {
    Serial.printf("[TWAI] install failed: %d\n", (int)err);
    _err_cnt++;
    return false;
  }

  err = twai_start();
  if (err != ESP_OK) {
    Serial.printf("[TWAI] start failed: %d\n", (int)err);
    _err_cnt++;
    return false;
  }

  Serial.println("[TWAI] started OK (ACCEPT_ALL)");
  _lastStatMs = millis();
  return true;
}

void SpeedCan::poll() {
  twai_message_t msg;

  // timeout=0 -> 非阻塞
  while (twai_receive(&msg, 0) == ESP_OK) {
    _rx_cnt++;

    Serial.print("[CAN] ID=0x");
    Serial.print(msg.identifier, HEX);
    Serial.print(" DLC=");
    Serial.print(msg.data_length_code);
    Serial.print(" DATA=");

    for (int i = 0; i < msg.data_length_code; i++) {
      if (msg.data[i] < 16) Serial.print('0');
      Serial.print(msg.data[i], HEX);
      Serial.print(' ');
    }
    Serial.println();
  }

  uint32_t now = millis();
  if (now - _lastStatMs >= 1000) {
    _lastStatMs = now;
    Serial.printf("[CAN] rx=%lu err=%lu\n", (unsigned long)_rx_cnt, (unsigned long)_err_cnt);
  }
}