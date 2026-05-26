#pragma once
#include <Arduino.h>

class PhiSensor {
public:
  void begin(int pin_adc);
  float read_rad();              // phi(rad) 连续角（unwrap）

  int raw_adc() const { return _raw; }
  float voltage() const { return _v; }

private:
  int _pin = -1;
  int _raw = 0;
  float _v = 0;
  float _adc_f = 0;
  float _phi_unwrapped = 0;
  bool _inited = false;
};