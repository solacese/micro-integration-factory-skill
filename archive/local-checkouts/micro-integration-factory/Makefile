SHELL := /bin/zsh

.PHONY: help install install-api install-web compose-up compose-down dev-api dev-worker migrate test lint format build-web deploy deploy-aws aws-status aws-down demo-ec2-up demo-ec2-down demo-ec2-status use-demo-openapi use-demo-postgres use-demo-hybrid preflight bootstrap

.DEFAULT_GOAL := help

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  %-20s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: install-api install-web ## Install all dependencies (API + web)

install-api: ## Install API dependencies
	cd apps/api && uv sync

install-web: ## Install web dependencies
	npm install

use-demo-openapi: ## Set up OpenAPI demo environment
	./infra/scripts/use_demo_env.sh openapi

use-demo-postgres: ## Set up PostgreSQL demo environment
	./infra/scripts/use_demo_env.sh postgres

use-demo-hybrid: ## Set up hybrid demo environment
	./infra/scripts/use_demo_env.sh hybrid

preflight: ## Validate environment configuration
	cd apps/api && uv run python ../../infra/scripts/preflight.py --env-file ../../.env

bootstrap: ## Bootstrap the entire project (install + compose + migrate)
	make install
	make compose-up
	make migrate

compose-up: ## Start local docker services (postgres, redis)
	docker compose -f infra/docker/compose.yaml up -d postgres redis

compose-down: ## Stop local docker services
	docker compose -f infra/docker/compose.yaml down

dev-api: ## Start API development server
	cd apps/api && PYTHONPATH=src uv run uvicorn spec2event.main:app --reload --host 0.0.0.0 --port 8000

dev-worker: ## Start background worker
	cd apps/api && PYTHONPATH=src uv run python -m spec2event.worker

migrate: ## Run database migrations
	cd apps/api && uv run alembic upgrade head

test: ## Run tests with coverage
	cd apps/api && uv run pytest --cov --cov-fail-under=60
	npm run typecheck:web

lint: ## Run linters (ruff + mypy for Python, ESLint for web)
	cd apps/api && uv run ruff check .
	cd apps/api && uv run mypy src/
	npm run lint:web

format: ## Format code with ruff
	cd apps/api && uv run ruff format .

build-web: ## Build web application
	npm run build:web

deploy: ## Fast deploy from .env, falling back to full AWS replacement when needed
	./infra/scripts/deploy.sh

deploy-aws: deploy ## Alias for deploy

aws-down: ## Tear down the AWS control plane
	cd apps/api && PYTHONPATH=src uv run python -m spec2event.control_plane down

aws-status: ## Check AWS control plane status
	cd apps/api && PYTHONPATH=src uv run python -m spec2event.control_plane status

demo-ec2-up: ## Launch EC2 control plane demo
	cd apps/api && PYTHONPATH=src uv run python -m spec2event.control_plane up

demo-ec2-down: ## Tear down EC2 control plane demo
	cd apps/api && PYTHONPATH=src uv run python -m spec2event.control_plane down

demo-ec2-status: ## Check EC2 control plane status
	cd apps/api && PYTHONPATH=src uv run python -m spec2event.control_plane status
