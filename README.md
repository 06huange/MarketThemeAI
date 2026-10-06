# MarketThemeAI

**Discovering emerging AI and semiconductor market themes from the news, without telling the model what to look for.**

🔗 **Live dashboard:** [market-theme-ai.vercel.app](https://market-theme-ai.vercel.app/)

---

## Why I built this

Anyone following the AI and chip industry is buried in news. Every week brings hundreds of articles about NVIDIA, TSMC, export controls, HBM memory, datacenter buildouts, and the stories that actually matter tend to show up as a *cluster* of coverage before they become an obvious headline.

Most tools for tracking this are keyword searches: you decide in advance that "advanced packaging" is a theme, and the tool counts mentions. That only finds what you already knew to look for.

MarketThemeAI takes the opposite approach. It reads each week's news, groups articles by **meaning** rather than keywords, and lets the themes emerge from the data. It then follows those themes week to week to answer:

- **What's new?** Themes that didn't exist last week.
- **What's growing?** Themes getting more coverage than before.
- **What's continuing or fading?** Stories that persist or lose attention.

## What it does

| | |
|---|---|
| **Corpus** | 8,000+ English news articles from global coverage via GDELT |
| **Coverage** | 60 companies across 13 industry groups (AI compute, foundry, memory, equipment, networking, EDA, packaging, …) |
| **Output** | 224 themes discovered across 14 weeks, each linked to its history and scored for "emergingness" |
| **Dashboard** | Summary stats, the hottest theme, filters for emerging / new / continuing themes, and theme trajectories over time |

## How it works

```
GDELT news index (BigQuery)
        │  query: English articles mentioning tracked companies or chip/AI topics
        ▼
Article download + text extraction        src/ingest/fetch_news.py
        │  parallel fetching, URL de-duplication, failure logging
        ▼
Relevance filter + company tagging        src/preprocess/filter_articles.py
        │  keep articles tied to the company universe; tag companies & groups
        ▼
Weekly embeddings + clustering            src/themes/build_weekly_themes.py
        │  sentence embeddings → HDBSCAN clusters → auto-generated labels
        ▼
Link themes across weeks                  src/track/link_themes_over_time.py
        │  match each theme to last week's by embedding similarity
        ▼
Score + export                            src/frontend_export/build_dashboard_data.py
        │  growth rate, new vs. continuing, emerging score
        ▼
Next.js dashboard (Vercel)                frontend/
```

## Key decisions

**GDELT through BigQuery instead of a news API.**
I started with GDELT's public API, but kept hitting rate limits and pulling in large amounts of noise. Its full index is available in BigQuery, so I query it there. That gives one SQL query with filtering by company, topic, and language before anything is downloaded, plus far more coverage than commercial news APIs offer for free.

**English-only.**
Embedding a mixed-language corpus risks clusters that split by *language* rather than *topic*. Restricting to English keeps clusters about the story, not the language it was written in.

**A curated company universe, but themes are not predefined.**
`data/company_universe.csv` lists the companies I care about, grouped into industry segments. It's used to filter out irrelevant articles and to explain each theme ("this cluster is mostly NVIDIA + TSMC → AI compute + foundry"). The groups never *define* the themes, though. Themes come purely from clustering, so the system can surface stories I didn't anticipate.

**Small, fast embeddings (`all-MiniLM-L6-v2`).**
Each article is embedded from its title plus the opening of the body. MiniLM runs on a laptop CPU for thousands of articles without a GPU, which keeps the pipeline cheap enough to rerun every week. A larger model is an easy swap later if topic separation needs to improve.

**HDBSCAN instead of k-means.**
The number of themes changes every week, and many articles don't belong to any theme. k-means would force me to pick *k* and assign every article somewhere. HDBSCAN finds however many dense clusters actually exist and labels the rest as noise, which matches how news really behaves.

**Cluster week by week, then link.**
Clustering all articles at once would blur time. Instead, each week is clustered independently, and themes are connected across weeks when their centroid embeddings have cosine similarity ≥ 0.72. This makes "new", "growing", and "fading" concrete, measurable ideas instead of guesses.

**A static frontend with no backend.**
The pipeline exports JSON and the dashboard reads it directly, so hosting is free and there's nothing to keep running. That was the right trade-off for a prototype. It's also the main thing I'm changing next (see below).

## Tech stack

**Data & ML:** Python, BigQuery (GDELT), trafilatura, sentence-transformers, HDBSCAN, scikit-learn (TF-IDF labeling), NumPy, pandas
**Frontend:** Next.js, React, TypeScript, Tailwind CSS, deployed on Vercel

## Current limitations

Being honest about what isn't solved yet:

- **Theme labels are rough.** Labels come from TF-IDF over article titles, which sometimes produces awkward phrases. An LLM-generated summary per cluster is the obvious improvement.
- **The emerging score is generous.** 185 of 224 themes are flagged as emerging, largely because 150 don't match any theme from the prior week and so count as "new". The linking and scoring thresholds need tuning against a hand-labeled sample.
- **The filter is permissive.** It keeps ~93% of articles, so market-wide stories that merely mention NVIDIA (e.g. geopolitics, stock-picking columns) still form their own themes.
- **Runs aren't scheduled yet.** `python -m src.pipeline` does everything from the BigQuery query to the dashboard export, but it still runs on demand; the cloud work below puts it on a weekly schedule.

## What's next: moving to cloud infrastructure

I'm turning the prototype into an automatically running service:

- **Containerize** the pipeline and a new query API with Docker
- **Run the pipeline weekly on AWS** (ECS Fargate scheduled tasks), storing results in S3
- **Serve the data through an API** (FastAPI on AWS Lambda) instead of static files
- **Define all infrastructure in Terraform** and deploy through **GitHub Actions** CI/CD
- **Monitor** runs with CloudWatch logs and alarms

The design goal is a system that refreshes itself every week and costs only a few dollars a month to run.

## Running it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# BigQuery access for the query step (bills to your GCP project; the
# script dry-runs first and refuses queries over 150 GB)
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-project-id

python -m src.pipeline                  # query → ingest → filter → themes → link → export
python -m src.pipeline --skip query     # reuse the last BigQuery result
python -m src.pipeline --from themes    # rerun clustering onward only

python -m pytest                        # tests

cd frontend && npm install && npm run dev
```

Article embeddings are cached in `data/embeddings/`, so after the first run each
weekly update only embeds the new articles.

## Repository layout

```
src/pipeline.py             runs every step in order
data/company_universe.csv   companies, aliases, industry groups, keywords
src/gkg/                    BigQuery query against the GDELT index
src/ingest/                 article download and text extraction
src/preprocess/             relevance filtering and company tagging
src/themes/                 weekly embedding, clustering, labeling
src/track/                  linking themes across weeks
src/frontend_export/        scoring and dashboard data export
frontend/                   Next.js dashboard
tests/                      unit tests, including the dashboard data contract
```
