CREATE TABLE merchants (
  merchant_id SERIAL PRIMARY KEY,
  name        TEXT NOT NULL,
  category    TEXT NOT NULL CHECK (category IN ('kuliner','ritel','transportasi','hiburan','jasa')),
  city        TEXT,
  mdr_rate    NUMERIC(5,4) NOT NULL
);
CREATE TABLE banks (
  bank_id SERIAL PRIMARY KEY,
  name    TEXT NOT NULL,
  type    TEXT NOT NULL CHECK (type IN ('bank','ewallet'))
);
CREATE TABLE transactions (
  txn_id      BIGSERIAL PRIMARY KEY,
  created_at  TIMESTAMP NOT NULL,
  merchant_id INT NOT NULL REFERENCES merchants,
  bank_id     INT NOT NULL REFERENCES banks,
  amount_idr  BIGINT NOT NULL CHECK (amount_idr > 0),
  method      TEXT NOT NULL CHECK (method IN ('QRIS','EWALLET','VA','CARD')),
  status      TEXT NOT NULL CHECK (status IN ('success','failed','pending')),
  fee_idr     BIGINT NOT NULL DEFAULT 0
);
