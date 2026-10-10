# usgs snapshot (authoring notes)

Not shipped to learners. The learner dataset folders `usgs/` and `usgs_gp/` (uploaded to the runner) contain only data files, so the agent cannot read the quirks listed here.

Source: USGS Earthquake Catalog, FDSN event API (https://earthquake.usgs.gov/fdsnws/event/1/), U.S. public domain. Credit "U.S. Geological Survey". Fetched once into `raw/` (frozen):

| File | Rows | Query |
|---|---|---|
| `raw/events_2026-06.csv` | 11,793 | `format=csv&orderby=time-asc&starttime=2026-06-01&endtime=2026-07-01` |
| `raw/events_2026-07.csv` | 12,201 | same, July |
| `raw/events_2026-08.csv` | 12,315 | same, August |
| `raw/deleted.csv` | 1,399 | `includedeleted=only`, 2026-06-01 to 2026-09-01 |

All magnitudes, worldwide.

Rebuild:

```
python build_usgs.py --fetch --clean-out <data>/usgs --gp-out <data>/usgs_gp   # re-downloads raw/, which changes the snapshot
python build_usgs.py --clean-out <data>/usgs --gp-out <data>/usgs_gp           # rebuilds from raw/; deterministic
```

## usgs/ (Course 2 lessons)

`days/YYYY-MM-DD.csv`, 92 files from 2026-06-01 to 2026-08-31, 41,387 rows, 8 MB, 341 to 596 rows per day (median 443). Each file holds what a feed would have published that day. Columns are the API's CSV columns unchanged: `time, latitude, longitude, depth, mag, magType, nst, gap, dmin, rms, net, id, updated, place, type, horizontalError, depthError, magError, magNst, status, locationSource, magSource`. Rows are sorted by `updated`.

How the feed is simulated from a single snapshot:

- Every event is published on the day of its `time`.
- About 12% of reviewed events (3,938) first appear as an `automatic` version with magnitude shifted by 0.1 to 0.4, location shifted by up to 0.08 degrees, depth shifted by up to 3 km, and quality columns blank. The real `reviewed` row is published 1 to 5 days later (the real gap between `time` and `updated`, capped at 5). 92 of those reviews fall after August 31 and are not published, so those events stay `automatic`. 3,846 ids appear as automatic then reviewed.
- 616 real deleted events (those with an `id` whose deletion falls in the window) first appear as `automatic` events, then as a `status=deleted` row on the day of the real deletion. The other 783 deleted rows have no `id` or are deleted after August 31 and are left out.
- `updated` is rewritten to the simulated publication time (a few minutes after `time`, plus the delay in days). The real `updated` values are not kept.
- Events in the API's own `automatic` status are published once and never revised.

Other real quirks, not in any answer key: non-earthquake `type` values (quarry blast, explosion, and others), small negative magnitudes, blank `mag` on some rows, mixed `magType` scales.

## usgs_gp/ (Course 2 GP)

Same feed with 16 planted issues. 91 day files, 40,526 rows.

The answer key `planted_issues.jsonl` has 41 issues, one JSON object each: `issue_id`, `type`, `day`, `source`, `details`. `source` is `planted` (16) or `real` (25). Real issues were already in the USGS data and are found by the same rules the reference monitor uses, so flagging them is not counted as a false positive:

- 19 `out_of_range`: one real longitude of -180.0155 (`us6000taxu`, 2026-07-01) and 9 `uw` events with the placeholder magnitude -5, each appearing on two days (automatic, then reviewed).
- 6 `cross_network_duplicate`: the same earthquake reported by two networks (mostly `ak` and `av` in Alaska), rows within 5 seconds and 0.1 degrees.

The clean `usgs/` feed contains the same real issues. They are not documented anywhere a learner's agent can read.

| Type | Count | What was done |
|---|---|---|
| `missing_day` | 1 | 2026-06-19 file removed |
| `duplicate_day` | 1 | 2026-07-03 file is a copy of 2026-07-02 |
| `depth_unit_change` | 3 | 2026-07-14 to 07-16 `depth` multiplied by 1000 (meters) |
| `out_of_range` | 4 | `mag` 12.3, `latitude` -97.5, `longitude` 212.4, `mag` -4.8 on single rows (event ids in key) |
| `cross_network_duplicate` | 5 | A reviewed event copied under a fictional network `ew` with a new id, time shifted 0.5 to 4 s |
| `volume_drop` | 1 | 2026-08-21 keeps 45 of 455 rows |
| `renamed_column` | 1 | From 2026-08-05 on, `mag` is named `magnitude` |
