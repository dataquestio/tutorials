# Data Collection Scripts

This folder contains three standalone data collection pipelines you can use to build a dataset for the **Vector Database Practice Project**. Each script collects real-world text data, normalizes it into a consistent schema, and saves outputs ready for chunking and embedding.

You only need to use **one** of these scripts to complete the project.

---

## Folder Structure

```

data-collection-scripts/
├── Guardian/
│   ├── collect_guardian_data.py
│   └── requirements.txt
├── Hugging-Face/
│   ├── collect_huggingface_data.py
│   └── requirements.txt
├── NewsAPI/
│   ├── collect_newsapi_data.py
│   └── requirements.txt
└── README.md

```

Each subfolder is self-contained, with its own script and dependency list.

---

## Recommended Setup

These scripts were tested with **Python 3.10**.

We strongly recommend using a virtual environment so dependencies for this project don’t conflict with other Python projects on your system.

### Create and Activate a Virtual Environment

From the project root (or inside a specific subfolder):

```bash
python -m venv venv
```

Activate it:

* macOS / Linux:

```bash
source venv/bin/activate
```
* Windows:

```bash
venv\Scripts\activate
```

Once activated, install dependencies using the `requirements.txt` file in the script’s folder.

---

## Choosing a Data Source

If you’re not sure where to start, use this guide:

| Script           | Best For                                | Tradeoffs                                    |
| ---------------- | --------------------------------------- | -------------------------------------------- |
| **Hugging Face** | Fastest setup, predictable text quality | Less realistic metadata                      |
| **Guardian**     | Rich articles with strong metadata      | Requires API key, moderate runtime           |
| **NewsAPI**      | Very recent, multi-source news          | Slowest, text quality varies due to scraping |

If you want the smoothest experience for chunking and evaluation, start with **Hugging Face**.

---

## Hugging Face Datasets

**Location:** `Hugging-Face/`

This script downloads one of several curated datasets from Hugging Face and saves it in a consistent format.

### What It Does

* Lets you choose between IMDb reviews, BBC News articles, or PubMed abstracts.
* No API keys required.
* No rate limits.
* Text is already included (no scraping step).

### Setup

```bash
cd Hugging-Face
pip install -r requirements.txt
```

### Run

```bash
python collect_huggingface_data.py
```

You’ll be prompted to choose a dataset. Press Enter to use the default.

### Outputs

* `*_documents.csv` — metadata for all documents
* `*_documents_full.json` — metadata plus full `body_text` for chunking

---

## The Guardian API

**Location:** `Guardian/`

This script collects recent Guardian articles across multiple sections such as politics, technology, science, sport, and culture.

### What It Does

* Collects ~2,000 articles with full text.
* Provides strong metadata for filtering (category, publication date, author, tags).
* Supports resuming if the script is interrupted.

### Setup

1. Get a Guardian API key: [https://open-platform.theguardian.com/access/](https://open-platform.theguardian.com/access/)

2. Create a `.env` file in the `Guardian/` folder:

```bash
GUARDIAN_API_KEY=your_key_here
```

3. Install dependencies:

```bash
cd Guardian
pip install -r requirements.txt
```

### Run

```bash
python collect_guardian_data.py
```

### Outputs

* `guardian_documents.csv`
* `guardian_documents_full.json`

---

## NewsAPI + Full-Text Scraping

**Location:** `NewsAPI/`

This script uses NewsAPI to discover articles and then attempts to extract full text from each article’s URL.

### What It Does

* Collects ~1,000 recent articles across several topics.
* Attempts full-text extraction by default.
* Falls back to description + truncated content when scraping fails.
* Saves progress so runs can be resumed.

### Important Notes

* Scraping is slower than the other scripts.
* Some sites block scraping (paywalls, anti-bot measures, JS-heavy pages).
* Expect some documents to be shorter or noisier than others.

### Setup

1. Get a NewsAPI key: [https://newsapi.org/register](https://newsapi.org/register)

2. Create a `.env` file in the `NewsAPI/` folder:

```bash
NEWSAPI_KEY=your_key_here
```

3. Install dependencies:

```bash
cd NewsAPI
pip install -r requirements.txt
```

### Run

```bash
python collect_newsapi_data.py
```

### Outputs

* `newsapi_documents.csv`
* `newsapi_documents_full.json`

---

## Output Format

All scripts produce the same core fields so downstream steps work unchanged:

* `id` (stable string identifier)
* `title`
* `body_text`
* `source`
* `category`
* `publication_date`
* `author`
* `url`
* `word_count`
* `summary`
* `tags`

The `*_documents_full.json` files are what you’ll use for chunking and embedding in the next step of the project.

---

## Verify Your Outputs

Before moving on, take a few minutes to confirm that your data looks reasonable:

* Check that the expected output files were created.
* Confirm you have roughly the expected number of documents (1,000–3,000).
* Open the JSON file and read 5–10 documents to understand length, structure, and metadata quality.

This will make chunking and evaluation decisions much easier later.

---

## `.env` Files and Git Hygiene

* Do **not** commit `.env` files containing API keys.
* Collected datasets can be large and may contain licensed text. Do not commit them unless the project instructions explicitly ask you to.
* Add the following to your `.gitignore` if needed:

```
.env
*_documents.csv
*_documents_full.json
newsapi_progress.csv
```

---

## Next Step

Once your data is collected and verified, return to the main project instructions and move on to **chunking and embedding**.

You do not need to rerun these scripts unless you want to switch data sources or experiment with a different domain.

