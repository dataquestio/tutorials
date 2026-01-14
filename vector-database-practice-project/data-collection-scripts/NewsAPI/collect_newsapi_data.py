"""
NewsAPI - Data Collection Script

What it does:
- Uses NewsAPI to discover recent articles (title, url, source, date, etc.)
- Optionally scrapes the URL to get full article text.
- Saves:
  - newsapi_documents.csv
  - newsapi_documents_full.json

Setup:
1) Get an API key: https://newsapi.org/register
2) pip install requests pandas tqdm python-dotenv trafilatura readability-lxml beautifulsoup4
3) Create .env in this folder:
   NEWSAPI_KEY=your_key_here
4) Run:
   python collect_newsapi_data.py

Notes:
- NewsAPI "content" is frequently truncated; scraping fixes that for many sites.
- Some sources block scraping (paywalls / anti-bot / scripts-only pages). That’s normal.
- A progress file is saved periodically so you can resume.
"""

import os
import re
import json
import time
import hashlib
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv

# Full-text extraction stack (two-pass approach)
import trafilatura
from readability import Document
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# -----------------------------
# CONFIG
# -----------------------------
load_dotenv()
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")

if not NEWSAPI_KEY:
    raise ValueError(
        "Missing NEWSAPI_KEY in .env.\n"
        "Get a key at https://newsapi.org/register\n"
        "Then create .env with: NEWSAPI_KEY=your_key_here"
    )

NEWSAPI_EVERYTHING_URL = "https://newsapi.org/v2/everything"

# Broad-ish topics that tend to yield lots of articles.
CATEGORIES = ["technology", "business", "science", "health", "sports"]
TARGET_TOTAL = 1000

# NewsAPI paging
PAGE_SIZE = 100  # max supported by NewsAPI
MAX_PAGES_PER_CATEGORY = 5  # 5 * 100 = 500 potential hits per category (before de-dupe)

# Time window: keep it recent so it’s easy to craft evaluation queries later.
DAYS_BACK = 30

# Toggle: if False, the script will skip scraping and use NewsAPI's description+content only.
SCRAPE_FULL_TEXT = True

# Scraping settings (conservative)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
}
TIMEOUT = 12
MAX_WORKERS = 5
DOMAIN_DELAY = 0.5
MAX_RETRIES = 1
MIN_TEXT_LEN = 200

# Progress / resume
PROGRESS_PATH = Path("newsapi_progress.csv")

# -----------------------------
# THREAD-SAFE GLOBALS (scraping)
# -----------------------------
domain_last_request_time = {}
domain_lock = Lock()
thread_local = threading.local()

# -----------------------------
# HELPERS
# -----------------------------
def utc_now():
    return datetime.now(timezone.utc)

def iso_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def get_domain(url: str) -> str | None:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return None

def throttle_domain(url: str):
    """
    Keeps the script from hammering one domain too quickly.
    This makes runs more stable and friendlier to websites.
    """
    domain = get_domain(url)
    if not domain:
        return

    with domain_lock:
        now = time.time()
        last = domain_last_request_time.get(domain)
        sleep_for = 0.0

        if last is not None:
            elapsed = now - last
            if elapsed < DOMAIN_DELAY:
                sleep_for = DOMAIN_DELAY - elapsed

        domain_last_request_time[domain] = now + sleep_for

    if sleep_for > 0:
        time.sleep(sleep_for)

def stable_id_from_url(url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"newsapi_{h}"

def clean_newsapi_content(text: str) -> str:
    """
    NewsAPI often appends things like: "... [+123 chars]"
    This strips that marker so chunking doesn't get weird artifacts.
    """
    if not text:
        return ""
    return re.sub(r"\s*\[\+\d+\s+chars\]\s*$", "", text).strip()

def extract_with_trafilatura(html: str) -> str | None:
    try:
        return trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
    except Exception:
        return None

def extract_with_readability(html: str) -> str | None:
    try:
        doc = Document(html)
        cleaned_html = doc.summary()
        soup = BeautifulSoup(cleaned_html, "html.parser")
        text = soup.get_text(separator="\n").strip()
        return text if len(text) >= MIN_TEXT_LEN else None
    except Exception:
        return None

def is_retryable(error_msg: str) -> bool:
    msg = (error_msg or "").lower()
    return (
        "timeout" in msg
        or "timed out" in msg
        or "connection" in msg
        or "429" in msg
        or "temporarily unavailable" in msg
    )

def scrape_one(url: str, idx: int):
    """
    Returns: idx, full_text, method_used, error, http_status, final_url
    """
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
    session = thread_local.session

    attempt = 0
    last_error = None

    while attempt <= MAX_RETRIES:
        try:
            throttle_domain(url)
            r = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            status = r.status_code
            final_url = r.url

            if status >= 400:
                return idx, None, None, f"http_{status}", status, final_url

            html = r.text

            text = extract_with_trafilatura(html)
            if text and len(text) >= MIN_TEXT_LEN:
                return idx, text, "trafilatura", None, status, final_url

            text = extract_with_readability(html)
            if text and len(text) >= MIN_TEXT_LEN:
                return idx, text, "readability", None, status, final_url

            return idx, None, None, "extraction_empty", status, final_url

        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES and is_retryable(last_error):
                attempt += 1
                time.sleep(1.2)
                continue
            return idx, None, None, last_error, None, None

    return idx, None, None, last_error, None, None

def fetch_newsapi_page(session: requests.Session, query: str, start: datetime, end: datetime, page: int):
    params = {
        "apiKey": NEWSAPI_KEY,
        "q": query,
        "from": iso_date(start),
        "to": iso_date(end),
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": PAGE_SIZE,
        "page": page,
    }

    r = session.get(NEWSAPI_EVERYTHING_URL, params=params, timeout=20)
    if r.status_code == 200:
        return r.json()

    # 429 commonly means daily quota exhausted
    if r.status_code == 429:
        raise RuntimeError(
            "NewsAPI quota exceeded (429). If you're on a free plan, try again later "
            "or reduce the number of pages/categories."
        )

    # 426 historically shows up for plan limitations on older content windows
    if r.status_code == 426:
        raise RuntimeError(
            "NewsAPI returned 426 (plan limitation). Try reducing DAYS_BACK and rerun."
        )

    try:
        msg = r.json().get("message")
    except Exception:
        msg = r.text

    raise RuntimeError(f"NewsAPI error {r.status_code}: {msg}")

def normalize_newsapi_article(article: dict, category: str) -> dict | None:
    url = article.get("url") or ""
    if not url:
        return None

    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()
    content = clean_newsapi_content(article.get("content") or "")

    published = article.get("publishedAt") or ""

    row = {
        "id": stable_id_from_url(url),
        "title": title or "(untitled)",
        "body_text": "",  # filled later (scrape or fallback)
        "source": (article.get("source") or {}).get("name") or "newsapi",
        "category": category,
        "publication_date": published,
        "author": (article.get("author") or "Unknown").strip() or "Unknown",
        "url": url,
        "word_count": 0,
        "summary": description,
        "tags": "",
        # Debug-ish columns are kept out of the “core schema”, but they’re useful in CSVs.
        "newsapi_content": content,
        "newsapi_description": description,
    }
    return row

def save_outputs(rows: list[dict], prefix: str):
    df = pd.DataFrame(rows)

    # Ensure core columns always exist, even if empty
    core_cols = [
        "id", "title", "body_text", "source", "category", "publication_date",
        "author", "url", "word_count", "summary", "tags"
    ]
    for c in core_cols:
        if c not in df.columns:
            df[c] = ""

    # Put core columns first for readability
    other_cols = [c for c in df.columns if c not in core_cols]
    df = df[core_cols + other_cols]

    csv_path = f"{prefix}_documents.csv"
    json_path = f"{prefix}_documents_full.json"

    df.to_csv(csv_path, index=False)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved: {csv_path}")
    print(f"✓ Saved: {json_path}")

def main():
    print("=" * 70)
    print("NewsAPI - Article Collection")
    print("=" * 70)
    print(f"Target total: ~{TARGET_TOTAL}")
    print(f"Categories: {', '.join(CATEGORIES)}")
    print(f"Window: past {DAYS_BACK} days (UTC)")
    print(f"Full-text scraping: {'ON' if SCRAPE_FULL_TEXT else 'OFF'}")
    print("=" * 70)

    end = utc_now()
    start = end - timedelta(days=DAYS_BACK)

    # Resume support: if progress exists, load it and skip already-seen URLs.
    existing = None
    if PROGRESS_PATH.exists():
        existing = pd.read_csv(PROGRESS_PATH)
        print(f"✓ Resuming from {PROGRESS_PATH} ({len(existing):,} rows)")
    else:
        existing = pd.DataFrame()

    seen_ids = set(existing["id"].tolist()) if "id" in existing.columns else set()
    rows = existing.to_dict("records") if not existing.empty else []

    # 1) Collect metadata from NewsAPI (title/url/date/source/description)
    with requests.Session() as session:
        for cat in CATEGORIES:
            if len(rows) >= TARGET_TOTAL:
                break

            print(f"\nCollecting metadata for category: {cat}")
            for page in range(1, MAX_PAGES_PER_CATEGORY + 1):
                if len(rows) >= TARGET_TOTAL:
                    break

                try:
                    payload = fetch_newsapi_page(session, query=cat, start=start, end=end, page=page)
                except Exception as e:
                    print(f"⚠️  Stopping category '{cat}' on page {page}: {e}")
                    break

                articles = payload.get("articles") or []
                if not articles:
                    break

                for a in articles:
                    row = normalize_newsapi_article(a, category=cat)
                    if not row:
                        continue
                    if row["id"] in seen_ids:
                        continue
                    rows.append(row)
                    seen_ids.add(row["id"])

                # Tiny pause for politeness
                time.sleep(1.0)

            print(f"✓ Metadata total so far: {len(rows):,}")

    # De-dupe again just in case (URL hashing should already do it)
    dedup = {}
    for r in rows:
        dedup[r["id"]] = r
    rows = list(dedup.values())

    # Trim to target size
    rows.sort(key=lambda x: x.get("publication_date", ""), reverse=True)
    rows = rows[:TARGET_TOTAL]

    # Save a checkpoint before scraping (so metadata-only still leaves a usable dataset)
    pd.DataFrame(rows).to_csv(PROGRESS_PATH, index=False)
    print(f"\n✓ Checkpoint saved: {PROGRESS_PATH}")

    # 2) Full text step
    if SCRAPE_FULL_TEXT:
        print("\nScraping full text from URLs (this can take a while)...")

        df = pd.DataFrame(rows)

        # If this is a resume run, keep already-scraped body_text.
        if "body_text" not in df.columns:
            df["body_text"] = ""
        df["body_text"] = df["body_text"].fillna("")

        # Only scrape rows that don't have usable text yet.
        pending_mask = df["body_text"].astype(str).str.len() < MIN_TEXT_LEN
        pending = df[pending_mask].copy()

        print(f"Pages to scrape: {len(pending):,} / {len(df):,}")

        if len(pending) > 0:
            futures = {}
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                for idx, row in pending.iterrows():
                    futures[ex.submit(scrape_one, row["url"], idx)] = idx

                completed = 0
                for fut in tqdm(as_completed(futures), total=len(futures), desc="Scraping"):
                    idx, full_text, method_used, error, status, final_url = fut.result()
                    completed += 1

                    if full_text and len(full_text) >= MIN_TEXT_LEN:
                        df.at[idx, "body_text"] = full_text
                    else:
                        # Fall back to description + truncated content if scraping failed.
                        # It’s not ideal, but it keeps the dataset usable for a smaller-scale run.
                        fallback = " ".join(
                            [
                                str(df.at[idx, "newsapi_description"] or "").strip(),
                                str(df.at[idx, "newsapi_content"] or "").strip(),
                            ]
                        ).strip()
                        df.at[idx, "body_text"] = fallback

                    df.at[idx, "word_count"] = len(str(df.at[idx, "body_text"]).split())
                    df.at[idx, "scrape_method"] = method_used or ""
                    df.at[idx, "scrape_error"] = error or ""
                    df.at[idx, "http_status"] = status if status is not None else ""
                    df.at[idx, "final_url"] = final_url or ""

                    # Save progress every so often so the run is resumable.
                    if completed % 200 == 0:
                        df.to_csv(PROGRESS_PATH, index=False)

            df.to_csv(PROGRESS_PATH, index=False)
            rows = df.to_dict("records")

    else:
        # Metadata-only mode: build body_text from description + NewsAPI content.
        # This is “good enough” for quick experiments, but chunking quality will suffer.
        for r in rows:
            fallback = " ".join([r.get("newsapi_description", ""), r.get("newsapi_content", "")]).strip()
            r["body_text"] = fallback
            r["word_count"] = len(fallback.split()) if fallback else 0

    # Final cleanup: drop rows with empty body_text (rare, but can happen)
    rows = [r for r in rows if (r.get("body_text") or "").strip()]
    rows.sort(key=lambda x: x.get("publication_date", ""), reverse=True)

    # Save final outputs
    save_outputs(rows, prefix="newsapi")

    # Leave PROGRESS_PATH in place as a “receipt” if something was blocked.
    # If you want a spotless directory, delete it manually after verifying outputs.

    print("\nDataset summary:")
    df = pd.DataFrame(rows)
    if not df.empty:
        print(df["category"].value_counts().to_string())
        print(f"\nAvg word_count: {df['word_count'].mean():.0f}")
        print(f"Word_count range: {df['word_count'].min():.0f}–{df['word_count'].max():.0f}")

if __name__ == "__main__":
    main()
