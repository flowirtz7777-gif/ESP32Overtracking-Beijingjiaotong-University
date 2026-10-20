from __future__ import annotations

from math import cos, sin, tan

import numpy as np

from common import Vehicle


PROCESSORS = {
    'phi_ekf_q025': {'process_std_deg_sqrt_s': .025, 'alpha_tau_s': 0.},
    'phi_ekf_q100': {'process_std_deg_sqrt_s': .1, 'alpha_tau_s': 0.},
    'phi_ekf_q025_alphaLP050': {'process_std_deg_sqrt_s': .025, 'alpha_tau_s': .05},
}
MEASUREMENT_STD_DEG = .25


def advance_phi(phi, alpha0, alpha1, speed, dt, vehicle):
    def rhs(value, alpha):
        yaw = speed * tan(alpha) / vehicle.l
        return yaw - (speed * sin(value) + vehicle.l_h * yaw * cos(value)) / vehicle.L
    mid = .5 * (alpha0 + alpha1)
    k1 = rhs(phi, alpha0)
    k2 = rhs(phi + .5 * dt * k1, mid)
    k3 = rhs(phi + .5 * dt * k2, mid)
    k4 = rhs(phi + dt * k3, alpha1)
    return phi + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6


def estimate(observed, processor, vehicle=Vehicle()):
    # Only sensor samples and their past/current timestamps enter this estimator.
    output = {key: np.asarray(observed[key]).copy() for key in ('time', 'state', 'alpha', 'v_B', 'measurement_time')}
    n = len(output['time'])
    if n == 0 or output['state'].shape != (n, 4):
        raise ValueError('Invalid observation shape')
    if processor == 'raw':
        output['phi_variance'] = np.full(n, np.deg2rad(MEASUREMENT_STD_DEG)**2)
        return output
    settings = PROCESSORS[processor]
    times = output['measurement_time']
    ages = output['time'] - times
    if np.any(np.diff(times) < -1e-10) or np.min(ages) < -1e-8 or np.max(ages) > .25 + 1e-8:
        raise ValueError('Measurement timestamps violate the registered causal range')
    measured = np.asarray(observed['state'])[:, 3]
    alpha = np.asarray(observed['alpha'])
    speed = np.asarray(observed['v_B'])
    R = np.deg2rad(MEASUREMENT_STD_DEG)**2
    Q_rate = np.deg2rad(settings['process_std_deg_sqrt_s'])**2
    phi, covariance = float(measured[0]), R
    trace = np.empty(n)
    trace[0] = covariance
    for k in range(1, n):
        dt = float(times[k] - times[k - 1])
        if dt > .1 + 1e-8:
            raise ValueError('Unregistered measurement gap')
        if dt > 1e-10:
            v = .5 * float(speed[k - 1] + speed[k])
            arguments = (float(alpha[k - 1]), float(alpha[k]), v, dt, vehicle)
            predicted = advance_phi(phi, *arguments)
            h = 1e-6
            F = (advance_phi(phi + h, *arguments) - advance_phi(phi - h, *arguments)) / (2 * h)
            prior = F * F * covariance + Q_rate * dt
            gain = prior / (prior + R)
            phi = predicted + gain * (float(measured[k]) - predicted)
            covariance = (1 - gain)**2 * prior + gain**2 * R
            tau = settings['alpha_tau_s']
            if tau:
                output['alpha'][k] = output['alpha'][k - 1] + dt / (tau + dt) * (alpha[k] - output['alpha'][k - 1])
        else:
            # A delayed packet repeated at startup is not a new measurement.
            output['alpha'][k] = output['alpha'][k - 1]
        output['state'][k, 3] = phi
        trace[k] = covariance
    if not np.all(np.isfinite(output['state'])) or np.any(trace < 0):
        raise AssertionError('Invalid state estimate or covariance')
    output['phi_variance'] = trace
    return output
