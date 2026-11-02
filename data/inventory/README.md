# Inventory database

Bago East and Bago West keep separate stock. This database holds the shared class list and the photo index. A photo is a reference, not a stock count. Loading a photo does not change either side's balances.

`data/inventory/pgdata/`, `data/inventory/objectDetect/`, and `data/Raw_Pic/` are local files and are not committed.

## Start PostgreSQL

From `data/inventory`:

```bash
docker compose up -d
```

PostgreSQL 16 comes up as `hydroflow-inventory-db`, database `inventory`, user `hydroflow`, password `hydroflow_dev`, published on port `5433`. Data is stored in `./pgdata`.

## Apply the schema

Apply the catalog first, then the region tables. `region_tables.sql` joins `inventory_categories` and `inventory_item_types`.

PowerShell, from `data/inventory`:

```powershell
Get-Content schema.sql -Raw | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U hydroflow -d inventory
Get-Content region_tables.sql -Raw | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U hydroflow -d inventory
```

Bash, from `data/inventory`:

```bash
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U hydroflow -d inventory < schema.sql
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U hydroflow -d inventory < region_tables.sql
```

## Load photos

## Catalog (v2)

Five default classes: **fund**, **foods**, **clothing**, **kitchenware**, **utilities**. Subclasses live in `inventory_item_types`; depot stock references those codes on `stock_balances`. The API can extend the catalog at runtime:

- `POST /inventory/catalog/categories` — add a class (`code`, `name`, `entry_mode`)
- `POST /inventory/catalog/categories/{code}/item-types` — add a subclass (`code`, `name`, `unit`)

Apply Alembic through `20261029_0009` (or fresh `schema.sql`) before relying on the new layout.

## Load photos

Put images under `data/inventory/objectDetect` (`Clothing` or legacy `Clothes`, `Foods`, `Kitchenware`, `Utilities` or legacy `Utility`, and `unassigned`). Set `INVENTORY_DATABASE_URL` (see `.env.example`), then from `backend`:

```bash
python -m app.cli load-inventory-images
```

Apply `schema.sql` before loading. If `inventory_images` is missing, the command stops with an error. The command rewrites `data/inventory/image_catalog.csv` from the stored photo rows and leaves East and West quantities unchanged.
