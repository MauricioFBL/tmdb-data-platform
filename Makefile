.PHONY: install lint format test test-unit test-integration dbt-run dbt-test

install:
	pip install -e ".[dev,spark,dbt]"

lint:
	ruff check .
	black --check .
	mypy ingestion glue

format:
	ruff check --fix .
	black .

test-unit:
	pytest tests/unit ingestion/tests glue/tests -v

test-integration:
	pytest tests/integration -v

test: test-unit test-integration

dbt-run:
	cd dbt && dbt run

dbt-test:
	cd dbt && dbt test
