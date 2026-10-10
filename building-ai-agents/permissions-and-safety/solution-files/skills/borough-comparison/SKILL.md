---
name: borough-comparison
description: Use only when a question ranks or compares boroughs, e.g. which borough is slowest or has the most requests.
---
# Borough comparison

Use this when a question ranks or compares boroughs.

## Groups

- The five boroughs are BRONX, BROOKLYN, MANHATTAN, QUEENS, and STATEN ISLAND.
- Report `Unspecified` rows separately with their count. Don't rank them with the boroughs.
- The data has no population figures. Don't invent per-capita numbers. If a question asks for rates, say that only counts and shares are available.

## Metrics

- Counts: report the count and each borough's share of the total.
- Time to close: parse `created_date` and `closed_date` with format `%m/%d/%Y %I:%M:%S %p`. Use the median, not the mean, because a few requests stay open for months. Leave out rows without a `closed_date`, rows where closing comes before creation, and say how many you left out.
- Open share: a request is open when `status` is anything other than `Closed`. Divide by all requests in the group.
- Always show the number of requests behind each figure. Flag any borough with fewer than 100 requests, since its figure is unreliable.

## Answer format

Start with the direct answer. Then give a table with one row per borough, sorted by the metric. End with what you left out and why.
