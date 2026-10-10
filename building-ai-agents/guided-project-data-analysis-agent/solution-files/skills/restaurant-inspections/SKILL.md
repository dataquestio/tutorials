---
name: restaurant-inspections
description: Use for any question about the NYC restaurant inspection data in data/inspections.csv.
---
# Restaurant inspections

## What a row is

Each row is one violation cited during one inspection, not one inspection. An inspection with four violations has four rows. To count inspections, first reduce to one row per inspection using the key `CAMIS`, `INSPECTION DATE`, `INSPECTION TYPE`. To count restaurants, count unique `CAMIS`.

## Quirks to handle

- `INSPECTION DATE` uses `MM/DD/YYYY`. Restaurants that haven't been inspected yet have the placeholder date `01/01/1900` and empty `INSPECTION TYPE`, `ACTION`, and `SCORE`. Leave them out of anything about inspections, and count them as "never inspected".
- `BORO` has a value `0` on a few hundred rows. Report it separately and don't rank it as a borough.
- `GRADE` letters A, B, and C are final grades. N, Z, and P mean the grade is pending. Use only A, B, and C when a question is about letter grades. A restaurant's most recent grade is the one with the latest `GRADE DATE`.
- `SCORE` is points for violations, so a lower score is better. It repeats on every violation row of the same inspection; take it once per inspection.
- `CRITICAL FLAG` is `Critical`, `Not Critical`, or `Not Applicable`. An inspection has a critical violation if any of its rows is `Critical`.
- `INSPECTION TYPE` combines a program and a stage, e.g. `Cycle Inspection / Initial Inspection` and `Cycle Inspection / Re-inspection`.

## Before answering

Reread the question and list every filter and threshold in it, such as "at least 300 restaurants" or "in 2025". Check that your code applies each one to the right unit: restaurants, inspections, or violation rows. "300 restaurants" is not "300 inspections".

## Answer format

Start with the direct answer. Say how you counted (rows, inspections, or restaurants) and which rows you left out and why.
