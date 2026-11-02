# nl2sql-id

Ask business questions about digital payments **in Indonesian** and get back the SQL, the result table, and a short summary.

> "Berapa success rate QRIS minggu lalu per kategori merchant?"

The focus is on evidence rather than the app: a frozen, verified test set, honest comparisons between approaches, and production-style safety and CI.

> **Status: early work in progress (dataset stage).** The smoke test is finished: a zero-shot local model, an execution-accuracy harness and a toy QLoRA run all work end to end on a 3-table toy schema. That schema has now been replaced by the full 8-table dataset. The real dev and test sets are being written next; no headline numbers are reported until they exist.

## What works today

- A PostgreSQL database (Docker) with an 8-table synthetic payments schema
- A **seeded** generator: one command always produces exactly the same ~300k transactions (Jan 2025 – Sep 2026) with Indonesian patterns: paydays, Harbolnas, Ramadan and Lebaran, bank incidents
- Invariant tests for the generator and the metrics (`uv run pytest`)
- An execution-accuracy harness with Wilson 95% confidence intervals
- A zero-shot baseline (`qwen2.5-coder:7b` on local Ollama) and a toy QLoRA run, both measured on 10 smoke-test questions (see [Smoke-test results](#smoke-test-results))

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

# 3. Fill the database with deterministic synthetic data (~3 s)
uv run python data/generate.py
# -> 5 banks, 7 promos, 500 merchants, 20000 users, 300000 transactions, 27288 failures, 3658 refunds

# 4. Run the tests
uv run pytest
```

Check that it worked:

```bash
docker compose exec db psql -U nl2sql -d payments \
  -c "SELECT SUM(amount_idr) AS gmv FROM transactions WHERE status = 'success'"
# -> 41841709300
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
app/
  pipeline.py       # question -> SQL -> rows (zero-shot baseline)
data/
  schema.sql        # table definitions, loaded by Postgres on first start
  generate.py       # seeded synthetic data generator
eval/
  metrics.py        # result comparison, Wilson interval
  harness.py        # runs a question set, writes eval/results/
  results/          # recorded runs (committed)
  review.py         # interactive review of unverified gold SQL
  test_questions.jsonl    # 100-question test set (30 easy / 40 medium / 30 hard)
  smoke_questions.jsonl   # 10 smoke-test questions (toy schema, retired)
training/
  make_toy_pairs.py # templated training pairs for the toy QLoRA run
  qlora-toy.ipynb   # Kaggle notebook
tests/              # metric and generator invariant tests
docker-compose.yml  # Postgres 16
pyproject.toml      # dependencies (exact versions pinned in uv.lock)
```

## Database

A fictional payment platform. All amounts are integer IDR; timestamps are local time (WIB).

| Table | Rows | Contents |
|---|---|---|
| `merchants` | 500 | category (kuliner, ritel, transportasi, hiburan, jasa), city, `joined_at`, `mdr_rate` |
| `users` | 20,000 | city, `registered_at`, segment (reguler, premium, bisnis) |
| `banks` | 5 | 3 banks and 2 e-wallets, all with generic names |
| `promos` | 7 | Ramadan, Harbolnas, gajian, Kemerdekaan, 9.9 |
| `transactions` | 300,000 | amount, method (QRIS, EWALLET, VA, CARD), status, promo, discount, fee |
| `failures` | 27,288 | one reason per failed transaction |
| `refunds` | 3,658 | at most one per transaction, full or partial |
| `settlements` | 142,304 | daily payout per merchant |

Patterns built into the data:

- Volume roughly doubles over the 21 months (platform growth), and merchants and users keep joining
- Gajian days (25th to 2nd) are about 30% busier; weekends about 15% busier
- Spikes on 9.9, 10.10, 11.11 and 12.12; Harbolnas days run at about 3× a normal day
- Ramadan is busier; the first two days of Lebaran are quieter
- Lunch and evening peaks (busiest hours: 12:00 and 19:00)
- Refund rates differ by category: ritel about 3%, kuliner about 0.2%
- Seven bank incident days on which one bank's failure rate jumps to about 50%, mostly `BANK_DOWNTIME`

## Business definitions

All gold SQL follows these definitions, so that "correct" has one meaning:

| Term | Definition |
|---|---|
| Transaksi sukses | `status = 'success'` |
| Success rate | successful / (successful + failed); pending is excluded |
| GMV | `SUM(amount_idr)` over successful transactions only; `amount_idr` is the price before any promo discount |
| MDR | merchant discount rate, the fee percentage charged to a merchant (`merchants.mdr_rate`) |
| Take rate | `SUM(fee_idr) / GMV`, successful transactions only |
| Refund rate | refunds of successful transactions created in the period / successful transactions created in the period |
| Settlement | payout to the merchant; `net_idr = gross_idr - fee_idr` |
| Promo cost | `SUM(discount_idr)` over successful transactions only; a failed payment gives no discount |
| Gajian period | the 25th through the 2nd of the next month |
| Minggu lalu / bulan lalu / kuartal kemarin | the previous full calendar week (Mon–Sun) / month / quarter |

Relative dates are resolved against a **fixed reference date of 2026-09-30** (a Wednesday), so every gold answer stays the same over time. "Minggu lalu" is therefore 21–27 September 2026.

## Data notes

Deliberate edge cases. Gold SQL has to handle each of them:

- **NULL city:** 620 users (about 3%) have no city. Questions grouped by user city will show a NULL group unless filtered.
- **Pending never resolves:** 9,016 transactions stay `pending` forever. They count as transactions but not as successes or failures.
- **Settlement is T+1:** a day's successful transactions are paid out the next day, so the last `settle_date` is 2026-10-01, one day past the transaction window.
- **Late refunds are cut off:** refunds dated after 2026-09-30 are not in the data. September 2026's refund rate (0.97%) is therefore lower than earlier months (about 1.4%), because some of its refunds have not happened yet.
- **Promo `end_date` is inclusive:** a promo ending on 12-12 covers that whole day, so filter with `created_at < end_date + 1`.
- **Discounts do not change GMV:** `discount_idr` is the promo subsidy; `amount_idr` is the full price.
- **Bank incident days** (date, bank): 2025-02-14 Bank Beta, 2025-05-20 Bank Alpha, 2025-08-05 Bank Gamma, 2025-11-11 Bank Alpha, 2026-01-12 Bank Beta, 2026-04-07 Bank Gamma, 2026-09-23 Bank Beta (inside "minggu lalu").

## Design decisions

- **Refund rate is dated by the transaction, not the refund.** Refunds are counted against the period in which the original transaction was created, so the numerator is a subset of the denominator and the rate cannot exceed 1. The cost is that recent periods look low until their refunds arrive (see Data notes).
- **`discount_idr` is a separate column.** `amount_idr` stays the full price, so GMV is unaffected by promos and promo cost can still be asked about.
- **User segments are fixed labels** (reguler, premium, bisnis). A time-relative segment such as "baru" (new) would depend on the reference date and make gold answers ambiguous.
- **The smoke set is retired, not ported.** Its 10 questions target the toy schema and were used to diagnose the baseline, so they are no longer fresh. The file and its recorded runs stay in git as history.
- **Database constraints before application code.** `CHECK` constraints reject bad rows at load time (for example, a fee on a failed transaction, or `net_idr ≠ gross_idr - fee_idr`); the tests cover rules that span tables.
- **Settlements are derived in SQL** from successful transactions, so they always agree with the transactions table.
- **Ramadan and Lebaran dates follow Kemenag:** Ramadan 2025 ran 1–30 March, with Idul Fitri on 31 March; Ramadan 2026 started 19 February, with Idul Fitri on 21 March.
- **The schema file is the baseline's schema prompt.** Its comments describe structure and units only, never business definitions; definitions belong to the glossary, which is a separate configuration in the ablations.

## Evaluation format

Each line of an eval file is one JSON object:

```json
{"id": "smoke_03", "question": "Berapa total GMV?", "gold_sql": "SELECT SUM(amount_idr) AS gmv FROM transactions WHERE status = 'success'", "difficulty": "easy", "tags": ["glossary:gmv"], "notes": "GMV counts successful transactions only.", "verified": false}
```

- **Primary metric:** execution accuracy. The predicted SQL and the gold SQL are both executed, and the result rows are compared. Row order is compared only when the gold SQL has `ORDER BY`.
- **`verified`:** only verified items count toward reported metrics. The 100-item test set (`eval/test_questions.jsonl`) was drafted and reviewed with an AI assistant; only `test_051` and `test_052` were also checked by hand. Every gold SQL was executed, top-N answers were checked for ties and near-ties at the cutoff, and the trickiest answers were cross-checked against independently written queries.
- **`notes`:** records how ambiguous questions were resolved. Ambiguity is reported as its own failure category, not hidden.

Run a question set with `uv run python -m eval.harness eval/<set>.jsonl`.

## Smoke-test results

10 hand-verified questions on the retired 3-table toy schema. With n = 10 the intervals are very wide, so these numbers only show that the pipeline works; they are not evidence about model quality.

| Model | Correct | 95% CI |
|---|---|---|
| `qwen2.5-coder:7b`, zero-shot (temperature 0) | 6/10 | 31–83% |
| `Qwen2.5-Coder-1.5B-Instruct`, base | 2/10 | 6–51% |
| `Qwen2.5-Coder-1.5B-Instruct` + toy QLoRA adapter | 6/10 | 31–83% |

The 7B baseline produced valid SQL for all 10 questions. Its failures:

- The reference-date line in the prompt led it to add date filters to questions that had no time window.
- It missed the glossary: GMV without the success filter, and a success rate that included pending and was multiplied by 100.
- It read "minggu lalu" as the last 7 days instead of the previous Monday–Sunday week.

The adapter's gain over the 1.5B base is not significant at n = 10, and its 51 templated training pairs sit close to the smoke questions. Its remaining failures match gaps in that training data: relative dates, grouping by the wrong table's `city`, and take rate.

## Roadmap

- [x] Postgres via Docker, toy schema, seeded generator
- [x] Smoke test end to end: one LLM call → SQL → execute → compare with gold
- [x] Execution-accuracy harness with confidence intervals
- [x] Full 8-table schema and ~300k transactions with realistic Indonesian patterns (payday, Harbolnas, Ramadan)
- [ ] 100-question test set (frozen) plus an informal/slang variant, and a separate dev set
- [ ] Ablations: schema selection, glossary, few-shot, retry-on-error
- [ ] QLoRA fine-tune of a small open model, compared with the zero-shot baseline
- [ ] SQL safety layer (SELECT-only, allow-list, read-only role, timeouts)
- [ ] FastAPI service, minimal Streamlit UI, CI with an accuracy gate
- [ ] Error analysis and results with confidence intervals

## Prior work

Text-to-SQL is not new, and Indonesian text-to-SQL work already exists, including academic datasets and the [`qrizan/nl2sql-id-qlora-3b`](https://huggingface.co/qrizan/nl2sql-id-qlora-3b) model, which targets SQLite. This project does not claim novelty. Existing work will be used as a baseline. The aim is execution quality: a payments domain, robustness to informal Indonesian, a safety layer, a CI quality gate, and honest error analysis.
