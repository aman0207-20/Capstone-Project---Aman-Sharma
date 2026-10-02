# Mamaearth Returns & Growth Intelligence Pipeline

Capstone project - Data Analytics with AI & Gen AI (E&ICT Academy IIT Roorkee).

**Business question:** returns seem to be eating into margins on a subset of orders. This repo proves it end-to-end
with three connected layers - a **SQL** store and reports, a **pandas** cleaning + analysis layer, and a
**GenAI narrator** that turns the verified numbers into a Situation-Complication-Resolution (SCR) brief for
regional ops and finance heads.

> No layer reports a number it did not compute itself or receive from the layer before it.

## Repo structure

```
.
├── README.md
├── sql/
│   ├── schema.sql          # Part 1 - creates database `mamaearth` + 3 tables (MySQL)
│   ├── seed_data.sql       # Part 1 - INSERTs generated from data/*.csv (blank cells -> NULL)
│   └── reports.sql         # Part 1 - 9 reports (a-i), actual output pasted above each query
├── data/
│   ├── customers.csv       # 45 rows   (provided, never edited)
│   ├── products.csv        # 16 rows   (provided, never edited)
│   └── orders.csv          # 180 rows  (provided, never edited)
├── analysis/
│   ├── clean_and_eda.py    # Part 2 - cleaning, EDA, and export of narrator/findings.json
│   └── visualize.py        # Part 2 - saves the two charts
├── visualizations/
│   ├── return_rate_by_payment.png
│   └── monthly_revenue_trend.png
└── narrator/
    ├── findings.json       # written by analysis/clean_and_eda.py (never hand-typed)
    └── generate_narrative.py   # Part 3 - Gemini narrator + offline fallback + numeric checker
```

## How data flows between the layers

```
data/*.csv ──► sql/ (MySQL)  : load raw data, run reports (raw revenue 99,860.20 = the "before cleaning" baseline)
     │
     └──────► analysis/clean_and_eda.py : independent pandas pipeline on the same raw CSVs
                   │  cleans (casing, duplicates, missing values), finds patterns, reconciles to the SQL total
                   ▼
              narrator/findings.json     : the verified numbers (written by the script, not by hand)
                   │
                   ├──► analysis/visualize.py  : charts (cross-checks itself against findings.json)
                   ▼
              narrator/generate_narrative.py : Gemini (or offline template) turns findings.json into the SCR narrative
```

Part 1 and Part 2 are independent (Part 2 reads the CSVs, not the database), so they can be run in either order.
Part 3 needs `narrator/findings.json`, which only exists after Part 2 has run.

## Prerequisites

- MySQL 8.x (or compatible) with a user that can create databases, and the `mysql` command-line client
- Python 3.10+
- Python packages:

```bash
pip install pandas matplotlib google-genai
```

(`google-genai` is only needed for the live Gemini path; the offline path works without a key.)

## Step 1 - SQL layer (MySQL)

Run from the repo root. Replace `root` with your MySQL user; you will be asked for the password.

```bash
mysql -u root -p < sql/schema.sql       # drops/recreates database `mamaearth` and the 3 tables
mysql -u root -p < sql/seed_data.sql    # loads 45 customers, 16 products, 180 orders
mysql -u root -p < sql/reports.sql      # runs reports (a) to (i)
```

Using MySQL Workbench instead: open each file and run it in the same order (schema -> seed_data -> reports).

Checks after seeding: `SELECT COUNT(*) FROM customers;` -> 45, `products` -> 16, `orders` -> 180.

Notes:
- Everything is loaded **raw** (duplicates included) so the reports show the "before cleaning" picture.
  Blank `discount_pct` / `rating` cells are loaded as real `NULL`s.
- `reports.sql` is the only file that changes the data (report (i) adds `customers.loyalty_tier`). To run it a second
  time, re-run `schema.sql` and `seed_data.sql` first, otherwise `ADD COLUMN` fails because the column already exists.
- Written for MySQL; it avoids SQLite-only syntax.

## Step 2 - Python/pandas layer

```bash
python analysis/clean_and_eda.py     # prints every intermediate result for Tasks 1-10
python analysis/visualize.py         # saves both PNGs into visualizations/
```

- `clean_and_eda.py` reads the raw CSVs in `data/`, prints each step, and **at the very end writes
  `narrator/findings.json`** (this export carries the Task 5 reconciliation figures: cleaned revenue 97,358.30,
  raw revenue 99,860.20, and the 2,501.90 duplicate delta, plus the return-rate, segment and monthly-peak results).
- `visualize.py` must run after `clean_and_eda.py`; it rebuilds the numbers from the raw CSVs and asserts they agree with
  `findings.json` before drawing.
- Both scripts can be re-run any time and regenerate identical numbers and files.

## Step 3 - GenAI narrator

```bash
python narrator/generate_narrative.py
```

**Option A - with Gemini (free key):**
1. Create a free API key in Google AI Studio (https://aistudio.google.com) - no payment needed.
2. Set it as an environment variable, then run the script:

```bash
# macOS / Linux
export GEMINI_API_KEY="your-key-here"

# Windows PowerShell
$env:GEMINI_API_KEY = "your-key-here"

# Windows CMD
set GEMINI_API_KEY=your-key-here

python narrator/generate_narrative.py --save-sample
```

`--save-sample` stores the output in `narrator/sample_output.txt`. Optional: set `GEMINI_MODEL` to use a different
model name than the default.

**Option B - no key at all (offline):**

```bash
python narrator/generate_narrative.py --offline
```

If no key is set, or the API call fails for any reason, the script automatically falls back to this deterministic
template path - no network, no key and no configuration needed.

**Numeric accuracy check:** every run prints a PASS/FAIL line for the five required figures (cleaned revenue
97,358.30; COD rate 44.4; COD + Tier-2 rate 54.5; duplicate delta 2,501.90; March with 20,318.90). To re-check a saved
file: `python narrator/generate_narrative.py --check-file narrator/sample_output.txt`.

## Key numbers you should be able to reproduce

| Layer | Result |
|---|---|
| SQL (a) | 180 orders, raw revenue 99,860.20, avg order value 554.78 |
| SQL (b) | 180 rows, 165 rated, 15 unrated |
| SQL (c) | Only customer with no orders: C045 Vihaan (LEFT JOIN and NOT IN agree) |
| SQL (d) | Jaipur 42.1%, Lucknow 30.6%, Bangalore 24.2% return rate |
| SQL (e) | Top 5: C043, C026, C008, C011, C042; OFFSET 2 returns ranks 3-5 |
| SQL (f) | Haircare 44,956.10 / Skincare 27,346.00 / Babycare 16,805.00 / PersonalCare 10,753.10 |
| SQL (g, h, i) | 10 names start with A; 4 acquisition sources; Gold 28 / Silver 17 |
| pandas | 7 -> 3 payment labels; 5 duplicates dropped (O0176-O0180); 175 clean rows; cleaned revenue 97,358.30 |
| pandas | Raw-vs-clean gap 2,501.90 = the 5 duplicates; outliers O0011 and O0098 (IQR upper bound 3.5) |
| pandas | Return rate: COD 44.4%, UPI 18.9%, CARD 14.7%; riskiest segment COD + Tier-2 = 54.5% |
| pandas | All six correlations negligible; "higher discounts reduce returns" is Busted (r = -0.088) |
| pandas | Outlier-corrected peak month is March (20,318.90); January's 29,582.10 was inflated by 2 bulk orders |
