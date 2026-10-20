#pragma once
#include <Arduino.h>

float lpf_update(float prev, float x, float k);
float wrap_pi(float a);
float unwrap_update(float prev_unwrapped, float new_wrapped);