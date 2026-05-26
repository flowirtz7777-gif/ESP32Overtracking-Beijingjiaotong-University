#include "sensors_phi.h"
#include "config.h"
#include "utils.h"

void PhiSensor::begin(int pin_adc) {
  _pin = pin_adc;

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  _adc_f = (float)analogRead(_pin);
  _phi_unwrapped = 0;
  _inited = true;
}

float PhiSensor::read_rad() {
  if(!_inited) return 0;

  _raw = analogRead(_pin);
  _adc_f = lpf_update(_adc_f, (float)_raw, LPF_K_PHI);

  _v = _adc_f * ADC_VREF / ADC_MAX;

  float phi_0_2pi = PHI_OFFSET_RAD + PHI_GAIN_RAD_PER_ADC * _adc_f;
  float phi_wrapped = wrap_pi(phi_0_2pi);
  _phi_unwrapped = unwrap_update(_phi_unwrapped, phi_wrapped);

  return _phi_unwrapped;
}