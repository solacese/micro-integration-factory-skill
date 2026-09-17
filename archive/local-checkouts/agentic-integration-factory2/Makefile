SHELL := /bin/zsh

.PHONY: install install-api install-web compose-up compose-down dev-api dev-worker migrate test lint format build-web demo-ec2-up demo-ec2-down demo-ec2-status use-demo-openapi use-demo-postgres use-demo-hybrid hybrid-validate preflight bootstrap

install: install-api install-web

install-api:
	cd apps/api && uv sync

install-web:
	npm install

use-demo-openapi:
	./scripts/use_demo_env.sh openapi

use-demo-postgres:
	./scripts/use_demo_env.sh postgres

use-demo-hybrid:
	./scripts/use_demo_env.sh hybrid

hybrid-validate:
	./scripts/use_demo_env.sh hybrid
	cd apps/api && uv run python -m spec2event.one_shot_hybrid --mode validate

preflight:
	cd apps/api && uv run python ../../scripts/preflight.py --env-file ../../.env

bootstrap:
	make install
	make compose-up
	make migrate

compose-up:
	docker compose -f infra/docker/compose.yaml up -d postgres redis

compose-down:
	docker compose -f infra/docker/compose.yaml down

dev-api:
	cd apps/api && uv run uvicorn spec2event.main:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	cd apps/api && uv run python -m spec2event.worker

migrate:
	cd apps/api && uv run alembic upgrade head

test:
	cd apps/api && uv run pytest
	npm run typecheck:web

lint:
	cd apps/api && uv run ruff check .
	npm run lint:web

format:
	cd apps/api && uv run ruff format .

build-web:
	npm run build:web

demo-ec2-up:
	cd apps/api && uv run python -m spec2event.control_plane up

demo-ec2-down:
	cd apps/api && uv run python -m spec2event.control_plane down

demo-ec2-status:
	cd apps/api && uv run python -m spec2event.control_plane status
