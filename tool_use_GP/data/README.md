# Data — Cedar Valley Spring Count Intake

Three messy sources + the reference data + an answer key. Everything is hand-authored so each agent branch fires at least once and the expected output is deterministic.

## Files
- `source1_logbook.txt` — transcribed paper logbook (8 observations)
- `source2_email.txt` — volunteer email prose (5 observations + noise to ignore)
- `source3_spreadsheet.json` — legacy hand-typed count sheet (7 rows)
- `taxonomy_subset.json` — bundled eBird reference excerpt (species + decoys + spuh entries)
- `aliases.json` — nickname/typo → speciesCode table
- `expected_outputs.json` — answer key (`clean_roster` + `review_queue`)

## Processing rules (make the answer key deterministic)
- **Order:** logbook → email → spreadsheet, top to bottom. `record_id`s assigned in commit order.
- **Dedup key:** `(species_code, ISO date, location lower+strip)`. **First committed wins**; later matches are flagged `possible_duplicate`, never merged.
- **Canonical sites:** `Cedar Ridge`, `Marsh`, `North Marsh`. Kept clean in the data so location doesn't add data-cleaning burden (that's a later course).
- **Count words:** `a`/`one`/singular → 1, `pair` → 2, `half a dozen` → 6. Unresolvable: `handful`, `flock`, `several`, `didn't count`, `a couple` *(a couple = 2, but only matters when the species also resolves)*.
- **Dates:** LLM-interpreted against each source's reference date (see `_date_anchors` in the answer key). `last week` is deliberately unrecoverable to a specific day.

## Branch coverage matrix
| Source | Raw note | Outcome | Why |
|---|---|---|---|
| logbook | 3 canada geese on the pond | **commit** obs-1 | clean |
| logbook | pair of mallards | **commit** obs-2 | count word → 2 |
| logbook | half a dozen cedar waxwings | **commit** obs-3 | count word → 6 |
| logbook | 2 Anna's hummingbirds | **commit** obs-4 | clean 🥚 |
| logbook | handful of grackles | flag **ambiguous_count** | species OK, count not |
| logbook | some kind of gull | flag **ambiguous_species** | resolves to spuh, don't guess |
| logbook | 1 red-tail overhead | **commit** obs-5 | nickname alias → rethaw |
| logbook | Canadas x12 (second group) | flag **possible_duplicate** | in-source dup of obs-1 🥚 |
| email | a couple hawks, couldn't tell which | flag **ambiguous_species** | spuh (hawk sp.) |
| email | a great blue heron | **commit** obs-6 | "a" → 1 |
| email | 2 wood ducks | **commit** obs-7 | clean |
| email | grumpy Anna's hummingbird | **commit** obs-8 | "one" → 1 🥚 |
| email | last week … flock of grackles | flag **missing_date** | date unrecoverable |
| spreadsheet | Canda Goose / 12 (est) / Cedar Ridge / 5/9 | flag **possible_duplicate** | cross-source dup of obs-1; typo normalized 🥚 |
| spreadsheet | Quiscalus mexicanus / 4 / Cedar Ridge / 5/10 | **commit** obs-9 | sci-name → grtgra 🥚 |
| spreadsheet | American Robbin / 5 / (blank) / 5/9/26 | flag **incomplete_record** | typo OK, location missing |
| spreadsheet | (blank) / 2 / Marsh / 5/9 | flag **incomplete_record** | no species |
| spreadsheet | Jackalope Warbler / 1 / Cedar Ridge / 5/11 | flag **out_of_taxonomy** | not a real species 🥚 |
| spreadsheet | Canadian Goose / 8 / North Marsh / 5/12 | **commit** obs-10 | misname normalized; new site 🥚 |
| spreadsheet | annas hummingbird / 3 / North Marsh / 5/12 | **commit** obs-11 | apostrophe/case normalized 🥚 |

Result: **11 committed, 9 flagged.** Every `reason` in the enum fires at least once.

## Easter eggs (🥚 for the content team)
- **Canada Goose** appears several ways — `canada geese`, `Canadas` (birder shorthand), `Canda Goose` (typo), `Canadian Goose` (the classic misname; the bird is *Canada* Goose), with `Branta canadensis` available as a sci-name path too. Great normalization spread.
- **Grackles** (Great-tailed Grackle, *Quiscalus mexicanus*) appear three ways — `handful of grackles` (flagged on count), `flock of grackles` last week (flagged on date), `Quiscalus mexicanus` (sci-name → clean commit). Great-tailed is the grackle whose range overlaps Anna's Hummingbird; Common Grackle is kept as an out-of-range decoy.
- **Anna's Hummingbird** (*Calypte anna*) appears three times, including a name-drop for the author, and tests apostrophe/case normalization (`annas hummingbird`).
- **Jackalope Warbler** — a fake bird, fires the out-of-taxonomy branch and gives the team a chuckle.

## Reason enum (note the addition)
`ambiguous_species | unknown_species | ambiguous_count | missing_date | possible_duplicate | out_of_taxonomy | incomplete_record`

`incomplete_record` is **new** vs. the original spec (covers missing required fields like species or location). `unknown_species` vs `out_of_taxonomy`: the data uses `out_of_taxonomy` for a named-but-nonexistent bird; `unknown_species` is reserved for a real-sounding name resolve can't confidently match. Update `ReviewItem` in the spec to match.

## To verify before shipping
The 9 primary species codes are standard eBird and high-confidence. Confirm these against the eBird taxonomy download / `/ref/taxonomy/ebird`:
- the two spuh entries (`gullsp`, `hawksp`) — code + sciName convention
- decoy codes/sci-names, especially `cacgoo1` and Cooper's Hawk (`Astur cooperii`, recently moved from *Accipiter*)

## Geography
Cedar Valley is fictional, but the species mix is now internally consistent for a western/Pacific-Southwest count: Anna's Hummingbird and Great-tailed Grackle ranges overlap across California and Arizona. Common Grackle (eastern) is intentionally present only as an out-of-range decoy in the taxonomy, never in the observations.
