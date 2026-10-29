# nl2sql-id

Ask business questions about digital payments **in Indonesian** and get back the SQL, the result table, and a short summary.

> "Berapa success rate QRIS minggu lalu per kategori merchant?"

The focus is on evidence rather than the app: a frozen, hand-verified test set, honest comparisons between approaches, and production-style safety and CI.

> **Status: early work in progress (smoke-test stage).** The database, data generator and first 10 evaluation questions exist. There is no LLM pipeline or results yet. Every number in this README will come from the evaluation harness; none are reported until then.

## What works today

- A PostgreSQL database (Docker) with a 3-table toy schema: `merchants`, `banks`, `transactions`
- A **seeded** synthetic data generator: the same command always produces exactly the same 1,000 transactions
- 10 smoke-test questions with gold SQL in [`eval/smoke_questions.jsonl`](eval/smoke_questions.jsonl), pending manual verification

All data is synthetic. No real company data, schemas or personal data are used.

## Quickstart

**Requirements:** [Docker](https://docs.docker.com/get-docker/) and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Fzzrr/nl2sql-id.git
cd nl2sql-id

# 1. Start Postgres (the schema is created automatically on first start)
docker compose up -d

# 2. Install Python 3.11 and the exact dependency versions from uv.lock
uv sync

# 3. Fill the database with deterministic synthetic data
uv run python data/generate.py
# -> Inserted 5 banks, 50 merchants, 1000 transactions
```

Check that it worked:

```bash
docker compose exec db psql -U nl2sql -d payments \
  -c "SELECT SUM(amount_idr) AS gmv FROM transactions WHERE status = 'success'"
# -> 85283500
```

If you get a different number, your data differs from the reference data and the gold answers will not match.

### Connection details

| Setting  | Value       |
|----------|-------------|
| Host     | `localhost` |
| Port     | `5432`      |
| Database | `payments`  |
| User     | `nl2sql`    |
| Password | `nl2sql`    |

These are local development credentials for synthetic data only. To point the generator at another database, set `DATABASE_URL`:

```bash
DATABASE_URL=postgresql://user:pass@host:5432/db uv run python data/generate.py
```

### Reset

```bash
uv run python data/generate.py   # restore the data (truncates and reinserts)
docker compose down -v           # delete the database entirely (needed after editing schema.sql)
```

## Repository layout

```
data/
  schema.sql        # table definitions, loaded by Postgres on first start
  generate.py       # seeded synthetic data generator
eval/
  smoke_questions.jsonl   # 10 smoke-test questions with gold SQL
docker-compose.yml  # Postgres 16
pyproject.toml      # dependencies (exact versions pinned in uv.lock)
```

## Business definitions

All gold SQL follows these definitions, so that "correct" has one meaning:

| Term | Definition |
|---|---|
| Transaksi sukses | `status = 'success'` |
| Success rate | successful / (successful + failed); pending is excluded |
| GMV | `SUM(amount_idr)` over successful transactions only |
| Take rate | `SUM(fee_idr) / GMV`, successful transactions only |
| Minggu lalu / bulan lalu | the previous full calendar week (Mon–Sun) / month |

Relative dates are resolved against a **fixed reference date of 2026-09-30**, so every gold answer stays the same over time.

## Evaluation format

Each line of an eval file is one JSON object:

```json
{"id": "smoke_03", "question": "Berapa total GMV?", "gold_sql": "SELECT SUM(amount_idr) AS gmv FROM transactions WHERE status = 'success'", "difficulty": "easy", "tags": ["glossary:gmv"], "notes": "GMV counts successful transactions only.", "verified": false}
```

- **Primary metric:** execution accuracy. The predicted SQL and the gold SQL are both executed, and the result rows are compared. Row order is compared only when the gold SQL has `ORDER BY`.
- **`verified`:** only items checked by hand count toward reported metrics.
- **`notes`:** records how ambiguous questions were resolved. Ambiguity is reported as its own failure category, not hidden.

## Roadmap

- [x] Postgres via Docker, toy schema, seeded generator
- [x] First 10 smoke-test questions
- [ ] Smoke test end to end: one LLM call → SQL → execute → compare with gold
- [ ] Full 8-table schema and ~300k transactions with realistic Indonesian patterns (payday, Harbolnas, Ramadan)
- [ ] 100-question test set (frozen) plus an informal/slang variant, and a separate dev set
- [ ] Ablations: schema selection, glossary, few-shot, retry-on-error
- [ ] QLoRA fine-tune of a small open model, compared with the API baseline
- [ ] SQL safety layer (SELECT-only, allow-list, read-only role, timeouts)
- [ ] FastAPI service, minimal Streamlit UI, CI with an accuracy gate
- [ ] Error analysis and results with confidence intervals

## Prior work

Text-to-SQL is not new, and Indonesian text-to-SQL work already exists, including academic datasets and the [`qrizan/nl2sql-id-qlora-3b`](https://huggingface.co/qrizan/nl2sql-id-qlora-3b) model, which targets SQLite. This project does not claim novelty. Existing work will be used as a baseline. The aim is execution quality: a payments domain, robustness to informal Indonesian, a safety layer, a CI quality gate, and honest error analysis.
