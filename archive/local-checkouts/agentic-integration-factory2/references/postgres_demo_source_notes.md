# PostgreSQL Demo Source Notes

These notes document the validated database source used by the prepared PostgreSQL and hybrid demo bundles.

## Connection

- database: `defaultdb`
- host: `pg-fc58f9d-solace-eaf8.e.aivencloud.com`
- port: `28975`
- user: `avnadmin`
- ssl mode: `require`

Connectivity was verified successfully on `2026-03-19`.

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

For the simplest credible filmed story:

- start with a read-only approach
- prefer initial snapshot plus incremental polling on `updated_at`
- only mutate data if a live-change demo is explicitly required and approved
