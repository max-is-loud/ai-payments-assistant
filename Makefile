.PHONY: install test lint seed

install:
	uv sync
	cd web && npm install

seed:
	uv run python -m seed $(ARGS)

test:
	uv run pytest

lint:
	uv run ruff check .
