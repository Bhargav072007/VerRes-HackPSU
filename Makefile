PYTHON ?= .venv/bin/python

.PHONY: run test e2e lint fmt openapi
run:
	$(PYTHON) -m uvicorn api.app.main:app --reload --host 127.0.0.1 --port 8000
test:
	$(PYTHON) -m pytest
e2e:
	STUBS=1 $(PYTHON) -m pytest tests/test_e2e.py
lint:
	$(PYTHON) -m ruff check api contracts tests
	$(PYTHON) -m ruff format --check api contracts tests
fmt:
	$(PYTHON) -m ruff check --fix api contracts tests
	$(PYTHON) -m ruff format api contracts tests
openapi:
	$(PYTHON) -c 'import json; from pathlib import Path; from api.app.main import app; Path("web/openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n")'
