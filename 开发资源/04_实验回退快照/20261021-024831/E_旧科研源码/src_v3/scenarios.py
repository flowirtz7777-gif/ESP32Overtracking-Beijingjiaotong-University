from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.integrate import quad

from common import Vehicle


def ramp_value(t, peak, rate, blend=.2):
    duration = peak / rate + blend
    t = np.asarray(t)
    value = np.where(t < blend, rate * t**2 / (2 * blend),
                     np.where(t <= duration - blend, rate * (t - blend / 2),
                              peak - rate * (duration - t)**2 / (2 * blend)))
    return np.where(t <= 0, 0, np.where(t >= duration, peak, value))


@dataclass(frozen=True)
class Maneuver:
    id: str
    speed: float
    peak: float
    entry_rate: float
    return_rate: float
    entry_duration: float
    plateau: float
    return_duration: float
    pre: float = 6.0
    post: float = 8.0

    @classmethod
    def from_spec(cls, spec, vehicle=Vehicle()):
        peak = math.radians(spec["alpha_peak_abs_deg"])
        entry = math.radians(spec["entry_rate_abs_deg_s"])
        returning = math.radians(spec["return_rate_abs_deg_s"])
        de, dr = peak / entry + .2, peak / returning + .2
        v = spec["v_B_mps"]
        area_entry = quad(lambda t: math.tan(float(ramp_value(t, peak, entry))), 0, de,
                          points=[.2, de-.2], epsabs=1e-12)[0]
        area_return = quad(lambda t: math.tan(peak-float(ramp_value(t, peak, returning))), 0, dr,
                           points=[.2, dr-.2], epsabs=1e-12)[0]
        plateau = (math.radians(spec["turn_heading_change_deg"]) * vehicle.l / v - area_entry - area_return) / math.tan(peak)
        if plateau < 0:
            raise ValueError(f"Infeasible turn for {spec['id']}: negative plateau")
        return cls(spec["id"], v, peak, entry, returning, de, plateau, dr)

    @property
    def return_start(self):
        return self.pre + self.entry_duration + self.plateau

    @property
    def turn_end(self):
        return self.return_start + self.return_duration

    @property
    def end(self):
        return math.ceil((self.turn_end + self.post) / .02 - 1e-10) * .02

    def alpha(self, time):
        time = np.asarray(time)
        entry = -ramp_value(time - self.pre, self.peak, self.entry_rate)
        returning = -self.peak + ramp_value(time - self.return_start, self.peak, self.return_rate)
        return np.where(time < self.return_start, entry, returning)

    def phases(self, time):
        return np.select([time < self.pre, time < self.pre+self.entry_duration,
                          time < self.return_start, time < self.turn_end], [0, 1, 2, 3], default=4).astype(np.int8)


def reference_rhs(state, alpha, speed, vehicle):
    # Reference equations are independent of the online prediction step.
    x, y, theta, phi = state
    yaw = speed * math.tan(alpha) / vehicle.l
    trailer_yaw = (speed*math.sin(phi) + vehicle.l_h*yaw*math.cos(phi)) / vehicle.L
    return np.array([speed*math.cos(theta), speed*math.sin(theta), yaw, yaw-trailer_yaw])


@dataclass(frozen=True)
class SinusoidalManeuver(Maneuver):
    @classmethod
    def from_spec(cls, spec, vehicle=Vehicle()):
        peak = math.radians(spec["alpha_peak_abs_deg"])
        entry = math.radians(spec["entry_rate_abs_deg_s"])
        returning = math.radians(spec["return_rate_abs_deg_s"])
        de, dr = peak*math.pi/(2*entry), peak*math.pi/(2*returning)
        area = quad(lambda t: math.tan(peak*.5*(1-math.cos(math.pi*t/de))), 0, de, epsabs=1e-12)[0]
        area += quad(lambda t: math.tan(peak*.5*(1+math.cos(math.pi*t/dr))), 0, dr, epsabs=1e-12)[0]
        plateau = (math.radians(spec["turn_heading_change_deg"])*vehicle.l/spec["v_B_mps"]-area)/math.tan(peak)
        if plateau < 0:
            raise ValueError("Infeasible sinusoidal final maneuver")
        return cls(spec["id"], spec["v_B_mps"], peak, entry, returning, de, plateau, dr)

    def alpha(self, time):
        time = np.asarray(time)
        entry = np.clip((time-self.pre)/self.entry_duration, 0, 1)
        returning = np.clip((time-self.return_start)/self.return_duration, 0, 1)
        return np.where(time < self.return_start, -self.peak*.5*(1-np.cos(np.pi*entry)),
                        -self.peak*.5*(1+np.cos(np.pi*returning)))


def integrate_reference(maneuver, dt=.005, vehicle=Vehicle()):
    time = np.arange(round(maneuver.end / dt) + 1) * dt
    state = np.empty((len(time), 4))
    state[0] = [0, 0, math.pi/2, 0]
    a0 = maneuver.alpha(time)
    ah = maneuver.alpha(time[:-1] + dt/2)
    for k in range(len(time)-1):
        s = state[k]
        k1 = reference_rhs(s, float(a0[k]), maneuver.speed, vehicle)
        k2 = reference_rhs(s+dt/2*k1, float(ah[k]), maneuver.speed, vehicle)
        k3 = reference_rhs(s+dt/2*k2, float(ah[k]), maneuver.speed, vehicle)
        k4 = reference_rhs(s+dt*k3, float(a0[k+1]), maneuver.speed, vehicle)
        state[k+1] = s + dt/6*(k1+2*k2+2*k3+k4)
    if np.max(np.abs(state[:, 3])) > math.radians(45):
        raise ValueError(f"Operating phi range exceeded without clamping: {maneuver.id}")
    if abs(state[-1, 2]) > 2e-5:
        raise ValueError(f"Heading does not complete 90deg: {maneuver.id}")
    return {"time": time, "state": state, "alpha": a0, "v_B": np.full(len(time), maneuver.speed),
            "true_phase": maneuver.phases(time)}
