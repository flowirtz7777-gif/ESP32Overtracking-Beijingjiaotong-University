"""Fixed higher-budget candidates for every and only exhausted path point."""
import numpy as np

SEED_BUDGET = 2048
REFINE_BUDGET = 131072
TIME_RESOLUTION = 1e-7
TOLERANCE = .050000001


def selected_indices(path, reason_flags, bit):
    budget = path['budget_exhausted']
    if budget.dtype != np.dtype(bool) or not np.array_equal(budget, (reason_flags & bit) != 0):
        raise ValueError('Every and only original budget-exhausted path point must be selected')
    return np.flatnonzero(budget)


def compute(kernel, xy, time, state, error, vehicle, budget):
    code = kernel.__code__
    result = kernel(xy, time, state, vehicle=vehicle, spatial_error_m=error, tolerance_m=TOLERANCE,
                    time_resolution_s=TIME_RESOLUTION, max_evaluations_per_interval=budget)
    result.pop('witness_pose')
    if kernel.__code__ is not code:
        raise RuntimeError('Frozen label kernel code object must not change')
    return result


def changed_points(a, b):
    if set(a) != set(b):
        raise ValueError('Complete original output schema required')
    changed = np.zeros(len(next(iter(a.values()))), bool)
    for key in a:
        left, right = a[key], b[key]
        if left.shape != right.shape or left.dtype != right.dtype:
            raise ValueError('Output dtype or shape changed')
        equal = left == right
        if left.dtype.kind == 'f':
            equal |= np.isnan(left) & np.isnan(right)
        if equal.ndim > 1:
            equal = np.all(equal, axis=tuple(range(1, equal.ndim)))
        changed |= ~equal
    return changed


def summarize(original, refined):
    changed = changed_points(original, refined)
    time_changed = changed_points({key: original[key] for key in ('contact_lower_s', 'contact_upper_s')},
                                  {key: refined[key] for key in ('contact_lower_s', 'contact_upper_s')})
    return {'points': len(changed), 'any_output_changed': int(changed.sum()),
            'contact_bounds_changed': int(time_changed.sum()),
            'original_budget_points': int(original['budget_exhausted'].sum()),
            'remaining_budget_points': int(refined['budget_exhausted'].sum()),
            'refined_status_counts': {str(k): int((refined['contact_status'] == k).sum()) for k in range(4)},
            'refined_contact_witnesses': int(np.isfinite(refined['contact_upper_s']).sum()),
            'refined_witnessed_edge_uncertain': int((np.isfinite(refined['contact_upper_s']) & ~refined['edge_certain']).sum())}
