#include "sensors_alpha.h"
#include "config.h"
#include "utils.h"

void AlphaSensor::begin(int pin_adc) {
  _pin = pin_adc;

  // ESP32 ADC 设置
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db); // ~0-3.6V

  _adc_f = (float)analogRead(_pin);
  _alpha_unwrapped = 0;
  _inited = true;
}

float AlphaSensor::read_rad() {
  if(!_inited) return 0;

  _raw = analogRead(_pin);
  _adc_f = lpf_update(_adc_f, (float)_raw, LPF_K_ALPHA);

  _v = _adc_f * ADC_VREF / ADC_MAX;

  // 占位标定：0..4095 -> 0..2pi
  float alpha_0_2pi = ALPHA_OFFSET_RAD + ALPHA_GAIN_RAD_PER_ADC * _adc_f;

  // 转为(-pi,pi]并展开为连续角
  float alpha_wrapped = wrap_pi(alpha_0_2pi);
  _alpha_unwrapped = unwrap_update(_alpha_unwrapped, alpha_wrapped);

  return _alpha_unwrapped;
}