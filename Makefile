.PHONY: install test test-cov test-unit test-integration test-e2e test-cli lint clean docs docs-serve

install:
	poetry install

test:
	poetry run pytest tests/ -v

test-cov:
	poetry run pytest tests/ -v --cov=aptdata --cov-report=term-missing --cov-fail-under=80

test-unit:
	poetry run pytest tests/ -v -m "not integration and not e2e"

test-integration:
	poetry run pytest tests/test_integration.py -v -m integration

test-e2e:
	poetry run pytest tests/test_e2e.py -v -m e2e

test-cli:
	./test_cli.sh

lint:
	poetry run ruff check aptdata/ tests/

lint-fix:
	poetry run ruff check --fix smart_data/ tests/

docs:
	poetry run mkdocs build

docs-serve:
	poetry run mkdocs serve

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf site/ coverage.xml .coverage
