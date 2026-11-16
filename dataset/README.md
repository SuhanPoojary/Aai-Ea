# AegisSupport demo dataset

This folder is a public-submission snapshot of the synthetic data used by the
AegisSupport demo. It is separate from the application's runtime data sources:
the backend still seeds and loads data from its existing files and database.

## Files

- `customers.csv` - 12 fictional seed customers (`C001` through `C012`).
  Fields: `id`, `name`, `tier`, `email`, `city`, `account_status`.
- `orders.csv` - 13 fictional seed orders from `backend/db/seed.py`.
  Fields: `id`, `customer_id`, `item`, `delivered_item`, `status`, `amount`,
  `payment_status`, `courier`, `eta`.
- `tickets.csv` - Support tickets currently present in the local demo SQLite
  database when this snapshot was created. These are runtime/demo records, not
  seed constants. Fields: `id`, `customer_id`, `order_id`, `issue`, `category`,
  `priority`, `team`, `status`, `sla_minutes`, `created_at`, `human_takeover`.
- `knowledge_base/articles.json` - An exact copy of
  `data/knowledge_base/articles.json`, containing the RAG knowledge-base
  documents KB-101 through KB-112, including KB-101, KB-102, KB-103, KB-104,
  KB-105, KB-107, KB-108, and KB-110.

## Source and safety

- Customer and order values were exported from the local SQLite database using
  the IDs defined by `backend/db/seed.py`.
- Ticket values were exported from the local SQLite database because there is
  no ticket seed list in `backend/db/seed.py`; tickets are created at runtime.
- The database file itself is intentionally not included.
- Login accounts, password hashes, conversation/event logs, API keys, `.env`
  files, and database credentials are intentionally excluded.
- The two additional customer rows present in the local database were not
  copied because they are not part of the documented synthetic seed set.
- CSV files use UTF-8 encoding with a header row. The JSON file retains the
  source document structure (`id`, `title`, `tags`, and `text`) used by the RAG
  pipeline.

This dataset is intended for inspection, demonstrations, tests, and college
submission. It is not a production customer export.
