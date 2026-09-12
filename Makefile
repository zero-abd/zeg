# Repo-wide shortcuts. Everything assumes a venv at .venv in the repo root.
AGENT   := services/agent
GATEWAY := services/gateway
PY      := $(CURDIR)/.venv/bin/python
PIP     := $(CURDIR)/.venv/bin/pip
BACKEND ?= mock

.PHONY: help setup test demo web gateway-setup gateway gateway-test

help:
	@echo "make setup          create .venv and install dev deps"
	@echo "make test           run the agent test suite"
	@echo "make demo           run a scripted interview through the mock backend"
	@echo "make web            run the landing page dev server"
	@echo "make gateway-setup  install the gateway's transport deps (aiortc, aiohttp)"
	@echo "make gateway        run the WebRTC gateway (BACKEND=mock|gb10)"
	@echo "make gateway-test   run the gateway test suite (no transport deps needed)"

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

# The gateway's transport deps are heavy (aiortc pulls PyAV); the agent and its
# tests stay stdlib-only, so this is a separate, opt-in install. The gateway
# package itself is run via PYTHONPATH like the agent, not installed; these are
# just its runtime deps (source of truth: services/gateway/pyproject.toml).
gateway-setup:
	$(PIP) install -q "aiortc>=1.6" "aiohttp>=3.9"

# The candidate opens http://<host>:8080 in a browser. mic needs HTTPS off
# localhost, see the gateway README for a tunnel.
gateway:
	cd $(GATEWAY) && PYTHONPATH=.:$(CURDIR)/$(AGENT) $(PY) -m gateway --backend $(BACKEND)

# Runs without gateway-setup: the bridge/framing/playback tests do not import aiortc.
gateway-test:
	cd $(GATEWAY) && PYTHONPATH=.:$(CURDIR)/$(AGENT) $(PY) -m pytest -q
