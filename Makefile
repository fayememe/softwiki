.PHONY: install init test clean

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
