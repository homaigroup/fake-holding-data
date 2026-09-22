# fake-holding-data

A synthetic data generator for a fictional multi-industry holding company
(retail, logistics, e-commerce, manufacturing, finance, real estate).
It produces a realistic, referentially-consistent relational dataset —
useful as test fixtures for **Text-to-SQL systems**, BI/analytics demos,
query-performance testing, or teaching SQL on a non-trivial schema.

The generated data is Persian/Iranian-flavored (Iranian national IDs with
valid check digits, Iranian phone number formats, Shamsi/Jalali dates,
Rial amounts, Persian city/province names) but the schema and generator
logic are generic and easy to adapt to other locales.

## What you get

- **61 tables** across 6 business domains, all sharing one holding-level
  layer (subsidiaries, departments, employees, payroll, ownership,
  chart of accounts, intercompany transactions, treasury).
- Valid foreign keys everywhere — every FK is drawn from an existing
  parent row, so the dataset is always referentially consistent.
- Slowly-changing-dimension (SCD) style history tables (payroll history,
  price history, ownership history).
- A **controllable percentage of dirty data** (nulls, inconsistent phone
  formats, outlier/negative amounts, duplicate-like records) to make the
  dataset useful for testing data-quality and cleaning logic, not just
  happy-path queries.
- Deterministic output: the same `--seed` always produces the same data.

## Domains

| Domain | Example tables |
|---|---|
| Holding (shared) | `holding_subsidiaries`, `departments`, `central_employees`, `central_payroll_history`, `ownership_structure`, `board_members`, `chart_of_accounts`, `consolidated_financial_statements`, `intercompany_transactions`, `treasury_accounts` |
| Retail | `stores`, `products_retail`, `product_price_history`, `inventory_stock`, `customers_loyalty`, `promotions`, `pos_transactions`, `pos_transaction_items` |
| Logistics | `warehouses`, `fleet_vehicles`, `drivers`, `routes`, `shipments`, `shipment_items`, `shipment_events`, `fuel_logs` |
| Digital / e-commerce | `online_customers`, `sellers_marketplace`, `product_catalog_digital`, `online_orders`, `order_items`, `payments_online`, `carts_abandoned`, `reviews_ratings`, `website_sessions` |
| Manufacturing | `factories`, `production_lines`, `suppliers_manufacturing`, `raw_materials`, `finished_products_mfg`, `bill_of_materials`, `work_orders`, `production_batches`, `quality_checks`, `machine_maintenance_logs` |
| Finance | `loan_contracts`, `installment_schedule`, `lease_contracts`, `collateral_assets`, `credit_risk_assessment` |
| Real estate | `contractors`, `construction_projects`, `project_budget_lines`, `building_units`, `unit_sales_contracts`, `installment_payments_realestate` |

## Requirements

- Python 3.8+
- `Faker` and `jdatetime`

```bash
pip install -r requirements.txt
```

If you hit an "externally managed environment" error on recent Linux
distros:

```bash
pip install --break-system-packages -r requirements.txt
```

or use a virtualenv:

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Quick start

```bash
python generate_ariana_data.py
```

With defaults, this writes one CSV file per table (61 files) to
`./ariana_fake_data/csv/`.

## Full example

```bash
python generate_ariana_data.py \
  --seed 42 \
  --scale medium \
  --dirty-rate 0.07 \
  --start-year 2022 \
  --end-year 2026 \
  --out-dir ./ariana_fake_data \
  --sqlite
```

## CLI options

| Option | Type | Default | Description |
|---|---|---|---|
| `--seed` | int | `42` | Random seed. Same seed → same dataset (reproducible). |
| `--scale` | `tiny` \| `small` \| `medium` \| `large` | `small` | Volume of transactional/fact tables. Dimension tables (categories, stores, ...) grow more mildly so the schema stays realistic. |
| `--dirty-rate` | float 0–1 | `0.05` | Fraction of dirty data: unexpected nulls, inconsistent phone formats, outlier amounts. Raise it (e.g. `0.15`) for stress-testing data-quality logic. |
| `--start-year` / `--end-year` | int | `2023` / `2026` | Gregorian year range for transactions, orders and events. |
| `--out-dir` | path | `./ariana_fake_data` | Output directory (created if missing). |
| `--csv` / `--no-csv` | flag | `--csv` (on) | Write one CSV file per table to `out-dir/csv/`. |
| `--sqlite` | flag | off | Also build a single `ariana.db` SQLite file with `CREATE TABLE` + full data — ready to query directly. |

Full flag reference is always available via:

```bash
python generate_ariana_data.py --help
```

### Scale guide

| Value | Approx. `pos_transactions` rows | Suggested use |
|---|---|---|
| `tiny` | ~1,000 | Fast logic/debug runs |
| `small` | ~5,000 | Development, initial testing (default) |
| `medium` | ~25,000 | Analytical query performance testing |
| `large` | ~100,000 | Volume/performance testing close to real scale |

All other transactional tables (online orders, shipments, work orders,
installments, ...) scale proportionally. At `--scale large` the full
dataset is on the order of **3+ million rows** across all 61 tables
(the biggest table, `inventory_stock`, alone is ~1.2M rows), and the
resulting `ariana.db` SQLite file is roughly **130 MB**.

## Using the output

### CSV (default)

Each table gets its own file in `ariana_fake_data/csv/`, e.g.
`central_employees.csv`, `pos_transactions.csv`, `loan_contracts.csv`.
Import these directly into PostgreSQL, MySQL, BigQuery, DuckDB, etc.

### SQLite (`--sqlite`)

A single `ariana_fake_data/ariana.db` file is created with every table,
a primary key on each, and all rows loaded — ready to query immediately:

```bash
sqlite3 ariana_fake_data/ariana.db
sqlite> .tables
sqlite> SELECT COUNT(*) FROM pos_transactions;
```

or from Python:

```python
import sqlite3
conn = sqlite3.connect("ariana_fake_data/ariana.db")
cur = conn.execute(
    "SELECT store_id, COUNT(*) FROM pos_transactions GROUP BY store_id"
)
print(cur.fetchall())
```

### Generating a large dataset on a remote machine

For `--scale large` you'll want real CPU/RAM/disk, not a laptop. A typical
workflow is to run the generator on a remote box over SSH and pull back
(or query in place) the resulting `ariana.db`:

```bash
# copy the script and requirements over
scp generate_ariana_data.py requirements.txt user@remote-host:~/

# install deps and generate on the remote host
ssh user@remote-host '
  python3 -m pip install --break-system-packages -r requirements.txt &&
  python3 generate_ariana_data.py --scale large --sqlite \
    --out-dir ~/ariana_fake_data
'

# sanity-check the resulting database
ssh user@remote-host "python3 -c \"
import sqlite3
c = sqlite3.connect('ariana_fake_data/ariana.db')
print(c.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=\\\"table\\\"').fetchone())
print(c.execute('SELECT COUNT(*) FROM pos_transactions').fetchone())
\""

# pull the database back to your machine
scp user@remote-host:~/ariana_fake_data/ariana.db ./ariana_fake_data/
```

A `--scale large --sqlite` run produces ~3.3M rows and a ~130 MB SQLite
file in a few minutes on a modern multi-core machine.

## Notes

- **Reproducibility**: with a fixed `--seed`, re-running the script on the
  same version always produces the exact same data — useful for comparing
  a system's behavior over time.
- **Referential integrity**: every foreign key is chosen from rows that
  actually exist in the parent table; invalid FKs are never generated.
- **Shamsi dates**: columns such as `pay_period` in
  `central_payroll_history` are computed in the Shamsi/Jalali calendar
  (requires `jdatetime`; if it's not installed, those columns are left
  empty and the rest of the script still runs without error).
- **National IDs**: generated with Iran's official check-digit algorithm
  (valid format, not a real person).
- **Extending the generator**: the code is split into seven focused
  methods (`gen_shared`, `gen_retail`, `gen_logistics`, `gen_digital`,
  `gen_manufacturing`, `gen_finance`, `gen_realestate`) inside
  `generate_ariana_data.py` — add a table or column by editing the
  relevant method.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'faker'` | `pip install Faker jdatetime` |
| Permission error during `pip install` | Use `--break-system-packages` or a virtualenv |
| Data volume looks too small | Increase `--scale` to `medium` or `large` |
| Run takes too long | Test with `--scale small` or `tiny` first; `large` is expected to take longer |

## License

MIT — see [LICENSE](LICENSE).
