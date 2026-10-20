"""All registered factor contrasts, without parameter selection or gate overrides."""
import numpy as np

CELLS = {'m20c0': 'w2000_m20_c0', 'm20c100': 'w2000_m20_c100',
         'm50c0': 'w2000_m50_c0', 'm50c100': 'w2000_m50_c100'}
PAIRS = [('confirmation_at_m20', 'm20c0', 'm20c100'),
         ('confirmation_at_m50', 'm50c0', 'm50c100'),
         ('margin_at_c0', 'm20c0', 'm50c0'),
         ('margin_at_c100', 'm20c100', 'm50c100')]
METRICS = ('right_miss', 'right_late', 'right_no_before', 'right_pct',
           'right_lead_p10_s', 'right_lead_median_s', 'negative_fp', 'negative_fp_pct',
           'frame_fpr_pct', 'common_2s_reference_fpr_pct')


def difference(after, before):
    if after is None or before is None:
        return None
    return after-before


def miss_indices(point, targets, positions, tag, score_end):
    ids = targets['reference_ids'][positions]
    contact = targets['contact_time'][positions]
    eligible = (~targets['front_ignored'][positions]) & (targets['edge'][positions] == 2)
    eligible &= np.isfinite(contact) & (contact >= 2-1e-9) & (contact <= score_end+1e-9)
    result = ids[eligible & ~np.isfinite(point[tag+'_valid'][positions])]
    return np.sort(result).astype(np.int32)


def contrasts(scores, misses, *, case, method, cohort, prefix):
    by_tag = {row['variant']: row for row in scores}
    if set(by_tag) != set(CELLS.values()) or len(scores) != 4:
        raise AssertionError('Exactly all four registered cells required')
    rows, arrays = [], {}
    for contrast, before, after in PAIRS:
        left, right = by_tag[CELLS[before]], by_tag[CELLS[after]]
        lost = np.setdiff1d(misses[CELLS[after]], misses[CELLS[before]], assume_unique=True).astype(np.int32)
        recovered = np.setdiff1d(misses[CELLS[before]], misses[CELLS[after]], assume_unique=True).astype(np.int32)
        key = prefix+'__'+cohort+'__'+contrast
        arrays[key+'__added'] = lost
        arrays[key+'__removed'] = recovered
        if len(lost)-len(recovered) != right['right_miss']-left['right_miss']:
            raise AssertionError('Lossless index contrast disagrees with exact miss count')
        rows.append({'case_id': case, 'core_id': method, 'cohort': cohort, 'contrast': contrast,
                     'before_variant': CELLS[before], 'after_variant': CELLS[after],
                     'metric_differences_after_minus_before': {key: difference(right[key], left[key]) for key in METRICS},
                     'added_miss_count': len(lost), 'removed_miss_count': len(recovered),
                     'added_miss_array': key+'__added', 'removed_miss_array': key+'__removed',
                     'undefined_metrics': [key for key in METRICS if left[key] is None or right[key] is None],
                     'unbiased_population_or_vehicle_causal_effect': False,
                     'conditional_lead_quantiles_have_different_detected_compositions': True})
    interaction = {}
    for metric in METRICS:
        high = difference(by_tag[CELLS['m50c100']][metric], by_tag[CELLS['m50c0']][metric])
        low = difference(by_tag[CELLS['m20c100']][metric], by_tag[CELLS['m20c0']][metric])
        interaction[metric] = difference(high, low)
    rows.append({'case_id': case, 'core_id': method, 'cohort': cohort,
                 'contrast': 'margin_confirmation_interaction',
                 'definition': '(m50c100-m50c0)-(m20c100-m20c0)',
                 'metric_difference_of_differences': interaction,
                 'undefined_metrics': [key for key, value in interaction.items() if value is None],
                 'unbiased_population_or_vehicle_causal_effect': False})
    return rows, arrays
