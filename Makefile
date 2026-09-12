# Repo-wide shortcuts. Everything assumes a venv at .venv in the repo root.
AGENT := services/agent
PY    := $(CURDIR)/.venv/bin/python

.PHONY: help setup test demo web

help:
	@echo "make setup   create .venv and install dev deps"
	@echo "make test    run the agent test suite"
	@echo "make demo    run a scripted interview through the mock backend"
	@echo "make web     run the landing page dev server"

setup:
	python3 -m venv .venv
	$(CURDIR)/.venv/bin/pip install -q pytest
	@echo "ready. try: make demo"

test:
	cd $(AGENT) && $(PY) -m pytest -q

demo:
	cd $(AGENT) && PYTHONPATH=. $(PY) -m zeg.cli

web:
	cd web && npm run dev
