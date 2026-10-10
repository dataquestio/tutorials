# nyc311 snapshot

Source: NYC Open Data, "311 Service Requests from 2020 to Present" (https://data.cityofnewyork.us/d/erm2-nwe9), full export downloaded 2026-09-29. NYC Open Data states there are no restrictions on the use of Open Data.

Rebuild: `python build_nyc311.py --source 311_Service_Requests_from_2020_to_Present_20260929.csv --out-dir <data>/nyc311` (about 3 minutes). The 15 GB source export is not in this repo; download it from the link above. The output folder contains only the CSV files that are uploaded as the learner dataset. This README is for authors and is never shown to learners or the agent.

## Files

| File | Rows | Size | Contents |
|---|---|---|---|
| `service_requests.csv` | 1,006,831 | 189 MB | One row per request created 2026-06-01 to 2026-08-31, 16 columns |
| `resolutions.csv` | 644 | 0.1 MB | `resolution_id` to resolution text lookup for `service_requests.csv` |
| `daily_counts.csv` | 1,084,472 | 44 MB | Requests per `date`, `problem`, `borough`, 2020-01-01 to 2026-09-28 |

## service_requests.csv

Values are copied unchanged from the source. Only the column selection, header names, and `resolution_id` differ.

| Column | Source column |
|---|---|
| `unique_key` | Unique Key |
| `created_date` | Created Date |
| `closed_date` | Closed Date |
| `agency` | Agency |
| `problem` | Problem (formerly Complaint Type) |
| `problem_detail` | Problem Detail (formerly Descriptor) |
| `additional_details` | Additional Details |
| `location_type` | Location Type |
| `incident_zip` | Incident Zip |
| `borough` | Borough |
| `status` | Status |
| `resolution_id` | Resolution Description, replaced by an id into `resolutions.csv` |
| `community_board` | Community Board |
| `latitude` | Latitude |
| `longitude` | Longitude |
| `channel` | Open Data Channel Type |

Dropped source columns are near-empty (taxi, bridge, highway fields, Due Date, Facility Type), constant (Park Facility Name, Park Borough), or duplicates of kept columns (Agency Name, Location, state plane coordinates, street and address fields, City, BBL, Council District, Police Precinct).

## daily_counts.csv

`date` is ISO (`YYYY-MM-DD`), derived from Created Date. `problem` and `borough` are copied unchanged. Counts cover every source row.

## Known quirks

- Dates in `service_requests.csv` keep the source format, `MM/DD/YYYY hh:mm:ss AM`. `closed_date` is empty for open requests.
- `2026-09-28` in `daily_counts.csv` is a partial day (395 requests against roughly 9,000 on a normal day). The export was taken early that morning.
- `problem` has 276 distinct values across all years, against about 180 in recent months. Categories were renamed and split over time, and capitalization is inconsistent (`UNSANITARY CONDITION` next to `Illegal Parking`).
- `borough` includes `Unspecified` (1,234 summer rows).
- 2.5% of summer rows have no `resolution_id`.
- Every text column is categorical or an agency template. There is no true free-text field.
