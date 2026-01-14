"""
The Guardian - Data Collection Script

What it does:
- Pulls ~2,000 recent Guardian articles across several sections.
- Saves:
  - guardian_documents.csv
  - guardian_documents_full.json

Setup:
1) Get an API key: https://open-platform.theguardian.com/access/
2) pip install requests pandas tqdm python-dotenv
3) Create a .env file in this folder:
   GUARDIAN_API_KEY=your_key_here
4) Run:
   python collect_guardian_data.py

Notes:
- Uses a stable string id (Guardian's content id).
- Writes a small progress file so you can resume if the run gets interrupted.
"""

import os
import json
import time
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv

# -----------------------------
# CONFIG
# -----------------------------
load_dotenv()
GUARDIAN_API_KEY = os.getenv("GUARDIAN_API_KEY")

if not GUARDIAN_API_KEY:
    raise ValueError(
        "Missing GUARDIAN_API_KEY in .env.\n"
        "Get a key at https://open-platform.theguardian.com/access/\n"
        "Then create .env with: GUARDIAN_API_KEY=your_key_here"
    )

BASE_URL = "https://content.guardianapis.com/search"

SECTIONS = ["politics", "technology", "science", "sport", "culture"]
ARTICLES_PER_SECTION = 400  # 5 * 400 = 2,000

# Guardian allows up to 200 per page in many cases, but 50 is conservative and reliable.
PAGE_SIZE = 50

# Date window (recent content tends to be friendlier for evaluation queries)
DAYS_BACK = 180

# Polite pacing
SLEEP_BETWEEN_REQUESTS_SEC = 0.25

# Resume support
PROGRESS_PATH = Path("guardian_progress.json")

# -----------------------------
# HELPERS
# -----------------------------
def utc_now():
    return datetime.now(timezone.utc)

def iso_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def stable_row_id(guardian_id: str) -> str:
    # Guardian IDs are already stable; this is just a fallback if needed.
    if guardian_id:
        return guardian_id
    return "guardian_" + hashlib.sha1(os.urandom(16)).hexdigest()[:16]

def load_progress():
    if not PROGRESS_PATH.exists():
        return {"completed_sections": [], "rows": []}
    with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_progress(state):
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def guardian_request(params, session: requests.Session, max_retries=5):
    """
    Basic retry with backoff.
    - 429: wait and retry
    - network blips: retry
    """
    backoff = 2.0
    for attempt in range(1, max_retries + 1):
        try:
            r = session.get(BASE_URL, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()

            # Rate limit / burst protection
            if r.status_code == 429:
                wait = min(60, int(backoff * attempt))
                print(f"⚠️  Rate limited (429). Sleeping {wait}s then retrying...")
                time.sleep(wait)
                continue

            # Other API errors: show message if present, then stop retrying.
            try:
                msg = r.json().get("response", {}).get("message") or r.json().get("message")
            except Exception:
                msg = None
            print(f"⚠️  API error {r.status_code}. {msg or ''}".strip())
            return None

        except requests.RequestException as e:
            if attempt == max_retries:
                print(f"❌ Network error after {max_retries} tries: {e}")
                return None
            wait = min(30, int(backoff * attempt))
            print(f"⚠️  Network error: {e}. Sleeping {wait}s then retrying...")
            time.sleep(wait)

    return None

def normalize_guardian_result(item: dict) -> dict | None:
    """
    Converts a Guardian API result into the unified row schema.
    Skips items without usable body text.
    """
    fields = item.get("fields") or {}
    body = fields.get("bodyText") or ""
    body = body.strip()

    if not body:
        return None

    tags = item.get("tags") or []
    tag_names = [t.get("webTitle") for t in tags if t.get("webTitle")]
    tags_str = ", ".join(tag_names) if tag_names else ""

    pub = item.get("webPublicationDate")  # ISO timestamp string
    title = item.get("webTitle") or ""

    row = {
        "id": stable_row_id(item.get("id")),
        "title": title,
        "body_text": body,
        "source": "the_guardian",
        "category": (item.get("sectionName") or item.get("sectionId") or "").strip() or "unknown",
        "publication_date": pub or "",
        "author": (fields.get("byline") or "Unknown").strip(),
        "url": item.get("webUrl") or "",
        "word_count": safe_int(fields.get("wordcount"), default=len(body.split())),
        "summary": (fields.get("trailText") or "").strip(),
        "tags": tags_str,
    }
    return row

def fetch_section(section: str, start_date: datetime, end_date: datetime, target_n: int, session: requests.Session):
    rows = []
    pages_needed = (target_n + PAGE_SIZE - 1) // PAGE_SIZE

    for page in tqdm(range(1, pages_needed + 1), desc=f"{section}"):
        params = {
            "api-key": GUARDIAN_API_KEY,
            "section": section,
            "from-date": iso_date(start_date),
            "to-date": iso_date(end_date),
            "page-size": PAGE_SIZE,
            "page": page,
            "order-by": "newest",
            "show-fields": "bodyText,wordcount,byline,trailText",
            "show-tags": "keyword",
        }

        data = guardian_request(params, session=session)
        if not data:
            break

        results = (data.get("response") or {}).get("results") or []
        if not results:
            break

        for item in results:
            row = normalize_guardian_result(item)
            if row:
                rows.append(row)

        # Polite pacing
        time.sleep(SLEEP_BETWEEN_REQUESTS_SEC)

        if len(rows) >= target_n:
            break

    # Guardian can occasionally return duplicates across pages if content changes quickly;
    # de-dupe on id to keep things tidy.
    dedup = {}
    for r in rows:
        dedup[r["id"]] = r

    out = list(dedup.values())
    out.sort(key=lambda x: x.get("publication_date", ""), reverse=True)
    return out[:target_n]

def main():
    end_date = utc_now()
    start_date = end_date - timedelta(days=DAYS_BACK)

    print("=" * 70)
    print("The Guardian - Article Collection")
    print("=" * 70)
    print(f"Sections: {', '.join(SECTIONS)}")
    print(f"Target: {ARTICLES_PER_SECTION * len(SECTIONS):,} articles")
    print(f"Date range: {iso_date(start_date)} to {iso_date(end_date)} (UTC)")
    print("=" * 70)

    state = load_progress()
    completed_sections = set(state.get("completed_sections", []))
    all_rows = state.get("rows", [])

    # For fast lookups + de-dupe while resuming
    by_id = {r["id"]: r for r in all_rows if r.get("id")}

    with requests.Session() as session:
        for section in SECTIONS:
            if section in completed_sections:
                print(f"✓ Skipping {section} (already collected)")
                continue

            print(f"\nCollecting section: {section}")
            section_rows = fetch_section(
                section=section,
                start_date=start_date,
                end_date=end_date,
                target_n=ARTICLES_PER_SECTION,
                session=session,
            )

            for r in section_rows:
                by_id[r["id"]] = r

            completed_sections.add(section)

            # Save progress after each section so an interruption is painless.
            state = {
                "completed_sections": sorted(list(completed_sections)),
                "rows": list(by_id.values()),
            }
            save_progress(state)

            print(f"✓ Collected {len(section_rows)} rows for {section}")

    # Final dataset
    rows = list(by_id.values())

    # Sort newest-first for nicer browsing
    rows.sort(key=lambda x: x.get("publication_date", ""), reverse=True)

    df = pd.DataFrame(rows)

    csv_path = "guardian_documents.csv"
    json_path = "guardian_documents_full.json"

    df.to_csv(csv_path, index=False)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    # Clean up progress file after success (keeps the folder tidy)
    if PROGRESS_PATH.exists():
        PROGRESS_PATH.unlink()

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)
    print(f"✓ Saved: {csv_path}")
    print(f"✓ Saved: {json_path}")

    if not df.empty:
        print("\nDataset summary:")
        print(df["category"].value_counts().to_string())
        print(f"\nAvg word_count: {df['word_count'].mean():.0f}")
        print(f"Word_count range: {df['word_count'].min():.0f}–{df['word_count'].max():.0f}")

if __name__ == "__main__":
    main()
