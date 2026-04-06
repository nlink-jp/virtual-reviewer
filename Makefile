.PHONY: build install dev test clean

build: install

install:
	uv sync

dev:
	uv sync --extra dev

test:
	uv run pytest tests/ -v

clean:
	rm -rf dist/ .pytest_cache/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
