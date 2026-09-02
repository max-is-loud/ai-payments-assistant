.PHONY: install test lint seed dev

install:
	uv sync
	cd web && npm install

seed:
	uv run python -m seed $(ARGS)

dev:
	./scripts/dev.sh

test:
	uv run pytest
	cd web && npm test

lint:
	uv run ruff check .
