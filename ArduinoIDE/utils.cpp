#include "utils.h"
//（小工具：低通滤波、角度unwrap）
float lpf_update(float prev, float x, float k) {
  return prev + k * (x - prev);
}

float wrap_pi(float a) {
  // wrap to (-pi, pi]
  return atan2f(sinf(a), cosf(a));
}

float unwrap_update(float prev_unwrapped, float new_wrapped) {
  // prev_unwrapped: 连续角
  // new_wrapped: (-pi, pi]
  float prev_wrapped = wrap_pi(prev_unwrapped);
  float delta = wrap_pi(new_wrapped - prev_wrapped);
  return prev_unwrapped + delta;
}