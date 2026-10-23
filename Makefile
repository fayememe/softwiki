.PHONY: install init test clean docker-build docker-up docker-down docker-logs ci-deploy

install:
	pip install -e .
	pip install -e ".[dev]"

init:
	mkdir -p data/raw/html data/raw/pdf data/raw/markdown data/raw/api
	mkdir -p data/processed/documents data/processed/chunks data/processed/embeddings data/processed/extracted
	mkdir -p data/exports/wiki/countries data/exports/wiki/organizations data/exports/wiki/topics data/exports/wiki/events data/exports/wiki/claims data/exports/wiki/reports
	python -c "import os; os.makedirs('data', exist_ok=True)"
	python scripts/init_db.py

test:
	pytest tests/

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

docker-build:
	TAG=$${TAG:-dev} docker compose build

docker-up:
	TAG=$${TAG:-dev} docker compose up -d --no-build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f --tail=100

ci-deploy:
	./scripts/ci-deploy.sh
