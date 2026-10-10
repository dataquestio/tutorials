---
name: data-quality-checks
description: How to check one day of the feed for data quality problems and how to flag each kind. Load it at the start of every data quality run.
---

# Data quality checks

1. Call `profile_day` for the day.
2. Flag every problem below with `flag_anomaly`, using exactly these `kind` values. One flag per problem.

| Problem in the profile | kind | event_ids |
|---|---|---|
| `file_exists` is false | `missing_day` | none |
| `same_content_as_previous_day` is true | `duplicate_day` | none |
| `columns_changed` has added or removed columns | `renamed_column` | none |
| `depth_median_km` is above 100 | `depth_unit_change` | none |
| each entry in `out_of_range_values` | `out_of_range` | that event's id |
| each pair in `possible_cross_network_duplicates` | `cross_network_duplicate` | both ids of the pair |
| `rows_vs_trailing_mean` is below 0.5 | `volume_drop` | none |

3. Do not flag anything else, such as large earthquakes, revisions, or deletions. That is another system's job.
4. Append one line to the progress log with `append_progress`: the day, the row count, and the kinds you flagged (or "clean").
5. Finish with a one-sentence summary.
