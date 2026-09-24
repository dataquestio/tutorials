"""Optional dev test of the deterministic machinery (no LLM, no network).
Run from the project folder, with deps installed:
    pip install -r requirements.txt && python validate_core.py
"""
from intake_server import resolve, validate, Roster

passed = 0
failed = 0


def check(label, got, want):
    global passed, failed
    if got == want:
        passed = passed + 1
        print(f"[PASS] {label}")
    else:
        failed = failed + 1
        print(f"[FAIL] {label}\n    got={got!r} want={want!r}")


def code_of(text):
    match = resolve(text)
    if match is None:
        return "no_match"
    return match["speciesCode"]


def category_of(text):
    match = resolve(text)
    if match is None:
        return "no_match"
    return match["category"]


print("--- resolve ---")
check("'Canda Goose' -> cangoo", code_of("Canda Goose"), "cangoo")
check("'Canadian Goose' -> cangoo", code_of("Canadian Goose"), "cangoo")
check("'Canadas' -> cangoo", code_of("Canadas"), "cangoo")
check("'Quiscalus mexicanus' -> grtgra", code_of("Quiscalus mexicanus"), "grtgra")
check("'annas hummingbird' -> annhum", code_of("annas hummingbird"), "annhum")
check("'red-tail' -> rethaw", code_of("red-tail"), "rethaw")
check("'mallards' -> mallar3", code_of("mallards"), "mallar3")
check("'American Robbin' -> amerob", code_of("American Robbin"), "amerob")
check("'Jackalope Warbler' -> no_match", code_of("Jackalope Warbler"), "no_match")
check("'gull' -> spuh", category_of("gull"), "spuh")
check("'some kind of gull' -> spuh", category_of("some kind of gull"), "spuh")
check("'a couple hawks' -> spuh", category_of("a couple hawks"), "spuh")

print("\n--- validate ---")
good = {"species_code": "grtgra", "common_name": "Great-tailed Grackle",
        "scientific_name": "Quiscalus mexicanus", "count": 4, "date": "2026-05-10",
        "location": "Cedar Ridge", "source": "spreadsheet"}
check("clean record valid", validate(good)["valid"], True)
bad_spuh = dict(good)
bad_spuh["species_code"] = "gullsp"
check("spuh code rejected", validate(bad_spuh)["valid"], False)
bad_count = dict(good)
bad_count["count"] = 0
check("zero count rejected", validate(bad_count)["valid"], False)
no_loc = dict(good)
no_loc["location"] = ""
check("missing location rejected", validate(no_loc)["valid"], False)
bad_date = dict(good)
bad_date["date"] = "2026-07-01"
check("date outside window rejected", validate(bad_date)["valid"], False)

print("\n--- roster: dedup + no double flag ---")
roster = Roster()
first = dict(good)
first["species_code"] = "cangoo"
first["date"] = "2026-05-09"
first["location"] = "Cedar Ridge"
roster.add(first)
again = dict(first)
again["location"] = "cedar ridge"
check("duplicate across case", roster.duplicate_of(again), "obs-1")
roster.flag("American Robbin", "spreadsheet", "incomplete_record")
roster.flag("American Robbin", "spreadsheet", "incomplete_record")
check("flag not double-queued", len(roster.review), 1)

print(f"\n{passed} passed, {failed} failed")
