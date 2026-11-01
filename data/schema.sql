-- All amounts are integer IDR. Timestamps are local time (WIB), no time zone.

CREATE TABLE merchants (
  merchant_id SERIAL PRIMARY KEY,
  name        TEXT NOT NULL,
  category    TEXT NOT NULL CHECK (category IN ('kuliner','ritel','transportasi','hiburan','jasa')),
  city        TEXT NOT NULL,
  joined_at   DATE NOT NULL,
  mdr_rate    NUMERIC(5,4) NOT NULL CHECK (mdr_rate >= 0 AND mdr_rate < 1)  -- 0.0070 = 0.7%
);

CREATE TABLE users (
  user_id       SERIAL PRIMARY KEY,
  city          TEXT,  -- NULL when unknown
  registered_at DATE NOT NULL,
  segment       TEXT NOT NULL CHECK (segment IN ('reguler','premium','bisnis'))
);

CREATE TABLE banks (
  bank_id SERIAL PRIMARY KEY,
  name    TEXT NOT NULL UNIQUE,
  type    TEXT NOT NULL CHECK (type IN ('bank','ewallet'))
);

CREATE TABLE promos (
  promo_id       SERIAL PRIMARY KEY,
  name           TEXT NOT NULL,
  start_date     DATE NOT NULL,
  end_date       DATE NOT NULL,  -- inclusive
  discount_type  TEXT NOT NULL CHECK (discount_type IN ('percent','fixed')),
  discount_value NUMERIC(12,2) NOT NULL CHECK (discount_value > 0),  -- percent: 10 = 10%; fixed: IDR
  CHECK (end_date >= start_date)
);

CREATE TABLE transactions (
  txn_id       BIGSERIAL PRIMARY KEY,
  created_at   TIMESTAMP NOT NULL,
  merchant_id  INT NOT NULL REFERENCES merchants,
  user_id      INT NOT NULL REFERENCES users,
  bank_id      INT NOT NULL REFERENCES banks,
  amount_idr   BIGINT NOT NULL CHECK (amount_idr > 0),  -- before discount
  method       TEXT NOT NULL CHECK (method IN ('QRIS','EWALLET','VA','CARD')),
  status       TEXT NOT NULL CHECK (status IN ('success','failed','pending')),
  promo_id     INT REFERENCES promos,  -- NULL when no promo
  discount_idr BIGINT NOT NULL DEFAULT 0 CHECK (discount_idr >= 0 AND discount_idr <= amount_idr),
  fee_idr      BIGINT NOT NULL DEFAULT 0 CHECK (fee_idr >= 0),
  CHECK (promo_id IS NOT NULL OR discount_idr = 0),
  CHECK (status = 'success' OR fee_idr = 0)
);

-- One row per failed transaction.
CREATE TABLE failures (
  txn_id      BIGINT PRIMARY KEY REFERENCES transactions,
  reason_code TEXT NOT NULL CHECK (reason_code IN
                ('INSUFFICIENT_BALANCE','TIMEOUT','BANK_DOWNTIME','USER_CANCELLED','FRAUD_BLOCK')),
  reason_text TEXT NOT NULL
);

-- At most one refund per transaction; partial refunds allowed.
CREATE TABLE refunds (
  refund_id   SERIAL PRIMARY KEY,
  txn_id      BIGINT NOT NULL UNIQUE REFERENCES transactions,
  amount_idr  BIGINT NOT NULL CHECK (amount_idr > 0),
  reason      TEXT NOT NULL,
  refunded_at TIMESTAMP NOT NULL
);

CREATE TABLE settlements (
  settlement_id SERIAL PRIMARY KEY,
  merchant_id   INT NOT NULL REFERENCES merchants,
  settle_date   DATE NOT NULL,
  gross_idr     BIGINT NOT NULL CHECK (gross_idr >= 0),
  fee_idr       BIGINT NOT NULL CHECK (fee_idr >= 0),
  net_idr       BIGINT NOT NULL,
  UNIQUE (merchant_id, settle_date),
  CHECK (net_idr = gross_idr - fee_idr)
);
