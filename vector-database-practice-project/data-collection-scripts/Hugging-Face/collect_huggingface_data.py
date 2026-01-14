"""
Hugging Face Datasets - Data Collection Script

What it does:
- Downloads one of a few curated datasets from Hugging Face.
- Saves:
  - hf_documents.csv
  - hf_documents_full.json

Setup:
1) pip install datasets pandas tqdm
2) Run:
   python collect_huggingface_data.py

Notes:
- No API keys.
- No rate limits.
- Text is already present (no scraping step).
"""

import json
from dataclasses import dataclass
from typing import Any

import pandas as pd
from datasets import load_dataset
from tqdm import tqdm

# -----------------------------
# CONFIG
# -----------------------------
# Kept deliberately small + predictable.
# If one of these datasets ever changes upstream, the error message will show exactly what broke.
DATASET_CONFIGS = {
    "A": {
        "label": "IMDb Movie Reviews (3,000)",
        "hf_name": "imdb",
        "split": "train[:3000]",
        "output_prefix": "hf_imdb",
    },
    "B": {
        "label": "BBC News (2,000)",
        "hf_name": "SetFit/bbc-news",
        "split": "train[:2000]",
        "output_prefix": "hf_bbc_news",
    },
    "C": {
        "label": "Scientific Papers (PubMed) (2,000)",
        "hf_name": "scientific_papers",
        "config": "pubmed",
        "split": "train[:2000]",
        "output_prefix": "hf_pubmed",
    },
}

DEFAULT_CHOICE = "B"

# -----------------------------
# HELPERS
# -----------------------------
def pick_dataset():
    print("=" * 70)
    print("Hugging Face dataset picker")
    print("=" * 70)
    for k, cfg in DATASET_CONFIGS.items():
        marker = " (default)" if k == DEFAULT_CHOICE else ""
        print(f"[{k}] {cfg['label']}{marker}")
    print()

    choice = input(f"Choose A/B/C (press Enter for {DEFAULT_CHOICE}): ").strip().upper()
    if not choice:
        return DEFAULT_CHOICE
    if choice in DATASET_CONFIGS:
        return choice
    print("Invalid choice, using default.")
    return DEFAULT_CHOICE

def safe_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    return str(x)

def unify_row(
    *,
    rid: str,
    title: str,
    body_text: str,
    source: str,
    category: str,
    publication_date: str = "",
    author: str = "Unknown",
    url: str = "",
    summary: str = "",
    tags: str = "",
):
    body_text = (body_text or "").strip()
    wc = len(body_text.split()) if body_text else 0
    return {
        "id": rid,
        "title": title.strip() if title else "",
        "body_text": body_text,
        "source": source,
        "category": category or "unknown",
        "publication_date": publication_date or "",
        "author": author or "Unknown",
        "url": url or "",
        "word_count": wc,
        "summary": summary or "",
        "tags": tags or "",
    }

def process_imdb(ds):
    out = []
    for i, item in enumerate(tqdm(ds, desc="Processing IMDb")):
        text = safe_text(item.get("text"))
        label = "positive" if int(item.get("label", 0)) == 1 else "negative"
        out.append(
            unify_row(
                rid=f"imdb_{i}",
                title=f"IMDb review #{i}",
                body_text=text,
                source="huggingface_imdb",
                category=label,
            )
        )
    return out

def process_bbc(ds):
    out = []
    # SetFit/bbc-news typically uses numeric labels; keep a mapping so the output is readable.
    label_map = {
        0: "business",
        1: "entertainment",
        2: "politics",
        3: "sport",
        4: "tech",
    }
    for i, item in enumerate(tqdm(ds, desc="Processing BBC News")):
        text = safe_text(item.get("text"))
        lab = label_map.get(int(item.get("label", -1)), "unknown")
        # Some versions include a title field, some don’t. If it exists, use it.
        title = safe_text(item.get("title")) or f"BBC article #{i}"
        out.append(
            unify_row(
                rid=f"bbc_{i}",
                title=title,
                body_text=text,
                source="huggingface_bbc_news",
                category=lab,
            )
        )
    return out

def process_pubmed(ds):
    out = []
    for i, item in enumerate(tqdm(ds, desc="Processing PubMed")):
        abstract = item.get("abstract")
        if isinstance(abstract, list):
            body = " ".join([safe_text(x) for x in abstract]).strip()
        else:
            body = safe_text(abstract).strip()

        article_id = safe_text(item.get("article_id"))
        title = safe_text(item.get("title")) or (f"PubMed abstract {article_id}" if article_id else f"PubMed abstract #{i}")

        out.append(
            unify_row(
                rid=f"pubmed_{article_id or i}",
                title=title,
                body_text=body,
                source="huggingface_scientific_papers_pubmed",
                category="medical_research",
            )
        )
    return out

def main():
    choice = pick_dataset()
    cfg = DATASET_CONFIGS[choice]

    print("\n" + "=" * 70)
    print(f"Downloading: {cfg['label']}")
    print("=" * 70)

    try:
        if "config" in cfg:
            ds = load_dataset(cfg["hf_name"], cfg["config"], split=cfg["split"])
        else:
            ds = load_dataset(cfg["hf_name"], split=cfg["split"])
    except Exception as e:
        raise RuntimeError(
            f"Failed to load dataset from Hugging Face.\n"
            f"Dataset: {cfg.get('hf_name')} (choice {choice})\n"
            f"Error: {e}"
        )

    if choice == "A":
        rows = process_imdb(ds)
    elif choice == "B":
        rows = process_bbc(ds)
    else:
        rows = process_pubmed(ds)

    # Some rows can be empty text if upstream has missing values; drop those.
    rows = [r for r in rows if r.get("body_text")]

    df = pd.DataFrame(rows)

    csv_path = f"{cfg['output_prefix']}_documents.csv"
    json_path = f"{cfg['output_prefix']}_documents_full.json"

    df.to_csv(csv_path, index=False)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

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
