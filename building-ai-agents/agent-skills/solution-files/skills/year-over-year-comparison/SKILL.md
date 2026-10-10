---
name: year-over-year-comparison
description: Use only when a question compares two or more different years, e.g. summer 2026 vs summer 2025. Not for questions about a single year.
---
# Year-over-year comparison

Use this when a question compares the same period in two or more years.

## Source

Use `data/daily_counts.csv` (columns `date`, `problem`, `borough`, `request_count`). It covers every year. `data/service_requests.csv` only covers one summer, so it can't answer year-over-year questions.

## Steps

1. Use the same calendar window in every year, e.g. June 1 to August 31. Count the days present in each window and confirm they match.
2. Check the last date in the file. If a window ends on it, that day may be partial. Compare its total with the days before it and leave it out if it is far lower.
3. Find the right problem names before filtering. Search case-insensitively for the topic (e.g. `rodent`, `rat`, `noise`) and list every matching `problem` value with its count per year. Problem names were renamed and split over the years, so a name that exists in one year may be missing or tiny in another. If that happens, say so and combine the names that mean the same thing, listing which ones you combined.
4. Report, for each group: the count in each year, the absolute change, and the percentage change.
5. Treat `Unspecified` borough rows as their own group and mention them, but don't rank them with the five boroughs.

## Answer format

Start with the direct answer. Then give a small table with the per-year counts and changes. End with what you checked: window lengths, partial days, and any problem names you combined or excluded.
