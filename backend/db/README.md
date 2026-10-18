# DB layer

## 1. `.env`

Create a `.env` file in the `backend/` directory and define a `DATABASE_URL` when needed.

Example:

```dotenv
DATABASE_URL=sqlite:////absolute/path/to/backend/data/app.db
```

If `DATABASE_URL` is not set, the application uses:

```text
sqlite:////absolute/path/to/backend/data/app.db
```

The path is resolved relative to the code location, not the current working directory.

## 2. Run migrations

From `backend/`:

```bash
alembic upgrade head
```

To roll back:

```bash
alembic downgrade base
```

## 3. Create a new migration

```bash
alembic revision -m "describe_change"
```

Then edit the generated file under `alembic/versions/`.

## 4. Load sender catalog

```bash
python -m db.seed_senders
```

This script is idempotent and only inserts new records.

## 5. Run tests

```bash
pytest
```

Use temporary SQLite data sources for test isolation.

## 6. Example usage

```python
from db.queries import select_rows

rows = select_rows("forms", filters={"status": "uploaded"}, order_by="-uploaded_at", limit=20)
```
