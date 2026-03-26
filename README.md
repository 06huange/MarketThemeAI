# MarketThemeAI

## Project Objective
The goal of this project is to detect **emerging AI / semiconductor market themes** from news articles and track how those themes evolve over time.

Instead of manually defining themes in advance, the project uses a news pipeline to:
1. collect relevant articles,
2. filter out noisy or irrelevant ones,
3. enrich articles with company and group information,
4. embed articles into semantic vectors,
5. cluster similar articles into themes,
6. compare themes week by week.

This makes the project a **theme discovery system**, not just a keyword search tool.

---

## Progress So Far

### 1. Defined the company universe
We created `data/company_universe.csv` with fields such as:

- `company`
- `ticker`
- `group`
- `keywords`

Example groups include categories like:
- AI compute
- foundry
- memory
- equipment
- networking

#### Why
This gives the project a structured universe of companies to anchor analysis around.  
The company list is later used for:
- query construction,
- company mention detection,
- group-level interpretation of themes.

---

### 2. Built a news ingestion pipeline
We implemented `src/ingest/fetch_news.py` to retrieve articles from GDELT.

The ingestion pipeline:
- builds a query using company names and relevant semiconductor / AI phrases,
- retrieves articles in daily windows,
- downloads article pages,
- extracts article text,
- stores raw results in `data/raw/articles.json`.

#### Why
GDELT provides broad global news coverage and is suitable for collecting large numbers of candidate articles.  
The purpose of this step is to create a **raw corpus** of potentially relevant news articles for later filtering and modeling.

---

### 3. Added rate-limit handling and English filtering
During ingestion, we encountered:
- GDELT rate limits,
- non-English articles,
- noisy matches from broad keyword search.

We updated the ingestion logic to:
- throttle requests,
- retry conservatively,
- constrain the query to English-language articles.

#### Why
Without this, the corpus contained too much noise and too many unusable articles.  
English-only filtering improves downstream embedding and clustering quality, since mixed-language corpora can produce clusters based on language rather than topic.

---

### 4. Collected a 30-day raw corpus
Using the current ingestion query, we collected roughly **2100 raw articles** over a 30-day window.

#### Why
A theme-discovery project needs a sufficiently large corpus for clustering to be meaningful.  
A few dozen articles are enough for debugging, but not for extracting recurring weekly themes.

---

### 5. Built article filtering
We implemented `src/preprocess/filter_articles.py` to remove clearly irrelevant articles.

Current filtering logic keeps an article if it:
- mentions at least one company from the company universe, **or**
- contains at least two domain-relevant keywords.

The filtered dataset is saved to:

- `data/processed/articles_filtered.json`

#### Why
Raw keyword-based retrieval inevitably includes false positives.  
Filtering improves the signal-to-noise ratio before embeddings and clustering, while still preserving broad coverage of relevant tech and semiconductor news.

---

### 6. Added metadata enrichment during filtering
The filtered articles now include additional fields such as:

- `matched_companies`
- `matched_keywords`
- `mentioned_groups`
- `company_count`
- `group_count`
- `keyword_count`

#### Why
These fields are not the final themes themselves.  
Instead, they provide structured metadata that helps later with:
- interpreting clusters,
- labeling discovered themes,
- analyzing which company groups are associated with each theme.

For example, if a cluster contains many articles mentioning NVIDIA and TSMC, the associated groups might be:
- AI compute
- foundry

That makes the cluster easier to interpret.

---

## Current Status
At this point, we have:

- a company universe,
- a working ingestion pipeline,
- a 30-day raw article corpus,
- a filtered and enriched article dataset.

This means the project is now ready for the first true modeling step:

### Next Step: Embeddings
We will convert each article into a semantic vector representation so that similar articles can later be clustered into themes.

---

## Planned Next Steps

### 7. Build embeddings
Generate one embedding per article using a sentence-transformer model.

#### Why
Embeddings allow semantic similarity comparisons beyond simple keyword matching.

---

### 8. Cluster articles into themes
Cluster the article embeddings so that each cluster represents a theme.

Examples of discovered themes might include:
- advanced packaging bottlenecks
- HBM / memory demand
- AI datacenter buildout
- export controls

#### Why
Themes should emerge from article similarity rather than being hardcoded manually.

---

### 9. Track themes over time
Count cluster frequency by week and compare theme activity across time windows.

#### Why
This is how the project identifies which themes are **emerging**, **stable**, or **fading**.

---

## Important Clarification
The `group` field in `company_universe.csv` is **not** the same as a theme.

- **Groups** are predefined metadata categories for companies.
- **Themes** are discovered later by clustering semantically similar articles.

So the groups help explain themes, but they do not define them.

---

## File Structure So Far

```text
MarketThemeAI/
├── data/
│   ├── company_universe.csv
│   ├── raw/
│   │   └── articles.json
│   └── processed/
│       └── articles_filtered.json
├── src/
│   ├── ingest/
│   │   └── fetch_news.py
│   └── preprocess/
│       └── filter_articles.py
└── README.md