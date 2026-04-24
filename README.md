# Bharat.Law Mini Legal Data Pipeline

This project implements a small, reproducible legal data pipeline:

1. Crawl seed URLs politely (static + JS-rendered pages)
2. Store raw HTML/PDF files and crawl metadata
3. Normalize raw content into clean Markdown
4. Create semantic chunks (400–800 tokens each)
5. Run hybrid legal NER (regex + spaCy)
6. Evaluate predictions against `data/gold_ner.jsonl`
7. Write a simple HTML metrics report

## Setup

Use Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Optional JS rendering support needs Playwright browser binaries:

```bash
python -m playwright install chromium
```

The pipeline still runs without Playwright; JS rendering is skipped gracefully.

## Docker (Bonus)

Build and run the entire pipeline inside Docker — no local Python needed:

```bash
docker build -t bharat-law-pipeline .
docker run bharat-law-pipeline
```

To persist output files on your machine:

```bash
docker run -v %cd%\output:/app/output bharat-law-pipeline
```

## One-Command Run

Unix/macOS/Linux:

```bash
./run.sh
```

Windows PowerShell:

```powershell
.\run.ps1
```

Direct Python command (recommended):

```bash
python scripts/run_pipeline.py --max-pages 50 --delay 0.8
```

Typical results with `--max-pages 50`:

```
Pages crawled:        47
Documents normalized: 46
Chunks created:       405
Avg tokens/chunk:     643.39
NER annotations:      8899
NER precision:        0.9733
NER recall:           0.9733
NER F1-score:         0.9733
```

If a seed site returns `403` or `404`, the crawler records that in `crawl_index.jsonl` and continues gracefully.

**Note on seed URLs:** At the time of submission, the three original assignment seed URLs return HTTP 404:
- `nujslawreview.org/articles-archives/` has been removed.
- `incometaxindia.gov.in/Pages/*.aspx` returns HTTP 404 but still serves the real page body (ASP.NET quirk).

To keep the pipeline meaningful, `data/seed_urls.json` also includes:
- Two working homepages (`NUJS_HOME`, `INCOME_TAX_HOME`) as additional depth-0 seeds.
- Wikipedia Wikipedia seeds are blocked by `robots.txt` — correctly skipped by the crawler.

All original assignment seeds are still crawled and recorded in `crawl_index.jsonl`.

If you already have `crawl_index.jsonl` and raw files, skip re-crawling:

```bash
python scripts/run_pipeline.py --skip-crawl
```

## Stage Commands

Run the full pipeline:

```bash
python scripts/run_pipeline.py --max-pages 50 --delay 0.8
```

Evaluate NER against gold dataset:

```bash
python scripts/evaluate_ner.py --gold data/gold_ner.jsonl --gold-text-mode
```

If comparing prediction file against gold spans:

```bash
python scripts/evaluate_ner.py --gold data/gold_ner.jsonl --pred ner/annotations.jsonl
```

Run unit tests:

```bash
pytest
```

## Outputs

| File | Description |
|---|---|
| `raw/<url_hash>.html` | Raw crawled HTML |
| `raw/<url_hash>.pdf` | Raw crawled/local PDF |
| `crawl_index.jsonl` | Crawl metadata (URL, status, timestamp) |
| `normalized/<url_hash>.md` | Cleaned Markdown text |
| `normalized_index.jsonl` | Normalization metadata (title, char count) |
| `chunks/chunks.jsonl` | Semantic chunks with section path + token estimate |
| `ner/annotations.jsonl` | Extracted entities per chunk |
| `reports/metrics.html` | HTML metrics dashboard |

## Seed URLs

```json
{
  "NUJS_LAW_REVIEW":        "https://nujslawreview.org/articles-archives/",
  "INTERNATIONAL_TAXATION": "https://incometaxindia.gov.in/pages/international-taxation.aspx",
  "TAX_FAQS":               "https://incometaxindia.gov.in/Pages/faqs.aspx",
  "NUJS_HOME":              "https://nujslawreview.org/",
  "INCOME_TAX_HOME":        "https://incometaxindia.gov.in/Pages/default.aspx",
  "WIKI_EVIDENCE_ACT":      "https://en.wikipedia.org/wiki/Indian_Evidence_Act,_1872",
  "WIKI_CPC":               "https://en.wikipedia.org/wiki/Code_of_Civil_Procedure_(India)",
  "WIKI_INCOME_TAX_ACT":    "https://en.wikipedia.org/wiki/Income_Tax_Act,_1961"
}
```

Wikipedia seeds are blocked by `robots.txt` and correctly skipped.

## Design Choices

- **Crawler:** Uses `robots.txt`, Chrome-style User-Agent (to avoid 403s), exponential backoff retries, URL deduplication, same-site link expansion, and depth limit of 3.
- **404-with-content handling:** `incometaxindia.gov.in` returns HTTP 404 but serves a full HTML body (>40 KB). The normalizer accepts these instead of discarding them.
- **JS detection:** Playwright is triggered only when visible text < 250 chars and script count ≥ 3. Optional — pipeline works without it.
- **HTML normalization:** Strips `<script>`, `<style>`, `<nav>`, `<footer>`, `<form>`. Preserves headings, lists, tables as Markdown.
- **PDF normalization:** Uses PyMuPDF (fallback: pypdf). Adds `## Page N` markers so chunks retain page metadata.
- **NEL bug fix:** PDF content contains `\x85` (NEL) characters. `json.dumps(ensure_ascii=False)` does not escape them, but `str.splitlines()` splits on them — breaking JSONL. Fixed by sanitizing these characters in `_clean_text()` and using `split("\n")` in the NER reader.
- **Chunking:** Splits on heading/paragraph boundaries. Target 280–520 words/chunk (≈ 420–780 tokens at 1.5× multiplier). Docs under 220 words are skipped (nav-only shells). 70-word overlap for continuity.
- **Token estimation:** `words × 1.5` — closer to tiktoken on English legal text than the naive 1.3× multiplier.
- **NER:** Hybrid — regex for `SECTION_REF`, `DATE`, `MONEY`, `ACT_NAME`, `NOTIFICATION`; spaCy `en_core_web_sm` + legal gazetteer for `ORG`.
- **Evaluation:** Exact `(chunk_id, label, start, end)` span matching. Gold file has 100 rows × 6 entities = 600 spans. F1 = 0.9733.
- **Local PDF:** `data/sample_docs/income_tax_act_excerpt.pdf` is a 6-page bundled excerpt (Income-tax Act, 1961). Registered as `local://...` in `crawl_index.jsonl` to exercise the PDF path end-to-end.

## Limitations and Improvements

- Crawler is intentionally small. Production version would add persistent crawl state, sitemap support, MIME sniffing, and per-domain budgets.
- JS detection is heuristic. Production would use domain-specific rendering rules and debug traces.
- Token counts use `words × 1.5` approximation. For production LLM indexing, switch to `tiktoken`.
- Legal NER regex rules are broad. More labeled data would enable model fine-tuning and fuzzy span matching.
- Many chunks have empty `entities: []` (navigation text, stubs). A post-filter step could skip entity-empty chunks for downstream use.
- Wikipedia seeds blocked by `robots.txt` — limits richness of crawled legal content.

## Bonus Items Included

| Item | Points |
|---|---:|
| `Dockerfile` | +5 |
| `pytest` unit tests (3 passing) | +3 |
| `reports/metrics.html` HTML report | +2 |
| **Total bonus** | **+10** |
