.PHONY: install test lint

install:
	uv sync
	cd web && npm install

test:
	uv run pytest

lint:
	uv run ruff check .
