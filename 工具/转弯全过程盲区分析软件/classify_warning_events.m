function event = classify_warning_events(contact_s, warning_s, horizon_s, end_s, warmup_s, threshold_s, contact_edges)
%CLASSIFY_WARNING_EVENTS Separate dangerous misses from negative-sample outcomes.
    if nargin < 7, contact_edges = strings(size(contact_s)); end
    event = strings(size(contact_s));
    dangerous = isfinite(contact_s);
    front = dangerous & string(contact_edges) == "FRONT";
    dangerous = dangerous & ~front;
    startup = dangerous & contact_s < warmup_s;
    miss = dangerous & ~startup & ~isfinite(warning_s);
    late = dangerous & ~startup & isfinite(warning_s) & contact_s-warning_s < threshold_s;
    event(startup) = "STARTUP_TRUNCATED";
    event(miss) = "POLYW_NO_HIT";
    event(late) = "BLINDSPOT_REACTION_INSUFFICIENT";
    event(dangerous & ~startup & ~miss & ~late) = "REACTION_TIME_SUFFICIENT";
    negative = ~isfinite(contact_s);
    event(negative & ~isfinite(warning_s)) = "CORRECT_REJECTION";
    warned_negative = negative & isfinite(warning_s);
    censored = warned_negative & (~isfinite(horizon_s) | warning_s+horizon_s > end_s+1e-9);
    event(censored) = "END_TRUNCATED";
    event(warned_negative & ~censored) = "FALSE_POSITIVE";
    event(front) = "FRONT_CONTACT_IGNORED";
end
