PYTHON ?= .venv/bin/python
RUFF ?= .venv/bin/ruff

.PHONY: test lint format
test:
	$(PYTHON) -m pytest -q

lint:
	$(RUFF) check api
	$(RUFF) format --check api

format:
	$(RUFF) format api
	$(RUFF) check --fix api
