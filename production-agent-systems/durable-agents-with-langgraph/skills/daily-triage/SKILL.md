---
name: daily-triage
description: Step-by-step procedure for processing one day of the earthquake feed. Load it at the start of every daily run.
---

# Daily triage

1. Call `day_summary` for the day. If the file is missing or the row count, columns, or statuses look unusual compared with the progress log, flag it with `flag_anomaly` (kind `feed_problem`).
2. Call `apply_day_to_catalog` for the day, exactly once.
3. Look at the result:
   - New events with magnitude 6.0 or higher: flag each one (kind `large_event`).
   - Revisions where the magnitude changed by 0.5 or more: flag them together (kind `large_revision`).
   - Deleted events: no flag unless more than 20 were deleted in one day (kind `many_deletions`).
4. If an event of magnitude 7.0 or higher appeared, load the `alert-policy` skill before doing anything else about it.
5. Append two or three lines to the progress log with `append_progress`: the day, row count, new, revised, and deleted counts, and what you flagged.
6. Finish with a one-paragraph summary of the day.
