# PostgreSQL Demo Source Notes

These notes document the validated database source shape used by the prepared PostgreSQL and hybrid demo bundles.

## Connection

Configure these values in your `.env` under the `SOURCE_DATABASE_*` variables:

- database: your target database name
- host: your PostgreSQL host
- port: your PostgreSQL port (typically `5432` or `28975` for managed services)
- user: your database user
- ssl mode: `require` (recommended for cloud-hosted databases)

## Visible Non-System Tables

- `public.alembic_version`
- `public.app_states`
- `public.events`
- `public.products`
- `public.products_backup_20260220`
- `public.sessions`
- `public.user_states`

## Recommended Demo Table

Use `public.products`.

Why:

- it looks like real business data
- it has a clear entity shape
- it supports a straightforward event story
- it avoids the internal application-state tables

## Useful Columns

- `id`
- `sku`
- `name`
- `category`
- `price`
- `stock_quantity`
- `created_at`
- `updated_at`

## Recommended Ingestion Strategy

For the simplest credible demo:

- start with a read-only approach
- prefer initial snapshot plus incremental polling on `updated_at`
- only mutate data if a live-change demo is explicitly required and approved
