.PHONY: install test lint fmt run up down logs tf-fmt tf-validate

install:
	pip install -r app/requirements-dev.txt

test:
	cd app && TESTING=true python -m pytest --cov=. --cov-report=term-missing

lint:
	cd app && ruff check .

fmt:
	cd app && ruff check --fix .

run:
	cd app && TESTING=true LOG_JSON=false uvicorn main:app --reload

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api

tf-fmt:
	cd terraform && terraform fmt -recursive

tf-validate:
	cd terraform && terraform init -backend=false && terraform validate
