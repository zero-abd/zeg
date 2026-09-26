# Repo-wide shortcuts. Everything assumes a venv at .venv in the repo root.
AGENT   := services/agent
GATEWAY := services/gateway
PY      := $(CURDIR)/.venv/bin/python
PIP     := $(CURDIR)/.venv/bin/pip
BACKEND ?= mock

VISION  := services/vision
VISION_BUILD := $(VISION)/build
# Where OpenCV's CMake config lives, if CMake cannot find it on its own (a source build
# from services/vision/scripts/build_opencv.sh goes to ~/.local/opencv).
OPENCV_DIR ?= $(if $(wildcard $(HOME)/.local/opencv/lib/cmake/opencv4),$(HOME)/.local/opencv/lib/cmake/opencv4,)
CMAKE   := $(if $(wildcard $(CURDIR)/.venv/bin/cmake),$(CURDIR)/.venv/bin/cmake,cmake)

.PHONY: help setup test demo web deck gateway-setup gateway gateway-test \
	vision-setup vision test-vision vision-eval-data vision-eval

help:
	@echo "make setup          create .venv and install dev deps"
	@echo "make test           run the agent test suite"
	@echo "make demo           run a scripted interview through the mock backend"
	@echo "make evals          run the scoring eval suite"
	@echo "                    one at a time: bias redteam consent asr gate gaming"
	@echo "make web            run the landing page dev server"
	@echo "make deck           rebuild the pitch deck into deck.html"
	@echo "make gateway-setup  install the gateway's transport deps (aiortc, aiohttp)"
	@echo "make gateway        run the WebRTC gateway (BACKEND=mock|gb10)"
	@echo "make gateway-test   run the gateway test suite (no transport deps needed)"
	@echo "make vision-setup   install the vision build tools (cmake, ninja, pybind11) into .venv"
	@echo "make vision         build zeg-gaze: C++ core, CLI, Python module (needs OpenCV)"
	@echo "make test-vision    GoogleTest suite plus the Python integration tests"
	@echo "make vision-eval-data  download the labelled clips, generate the synthetic ones"
	@echo "make vision-eval    precision/recall of flagged spans on the labelled clips"

setup:
	python3 -m venv .venv
	$(CURDIR)/.venv/bin/pip install -q pytest
	@echo "ready. try: make demo"

# Both tracks, because the gateway imports the agent package and a change on either
# side can break the other. Running only your own half is how that gets found late.
test: test-agent test-gateway

test-agent:
	cd $(AGENT) && $(PY) -m pytest -q

test-gateway:
	cd $(GATEWAY) && PYTHONPATH=.:../agent $(PY) -m pytest -q

demo:
	cd $(AGENT) && PYTHONPATH=. $(PY) -m zeg.cli

evals:
	cd $(AGENT) && PYTHONPATH=. $(PY) -m zeg.evals

bias:
	cd $(AGENT) && PYTHONPATH=. $(PY) -c "from zeg.evals.bias import run_pairs; print(run_pairs().render())"

redteam:
	cd $(AGENT) && PYTHONPATH=. $(PY) -c "from zeg.evals.redteam import run_redteam; print(run_redteam().render())"

consent:
	cd $(AGENT) && PYTHONPATH=. $(PY) -c "from zeg.evals.consent import run_consent; print(run_consent().render())"

asr:
	cd $(AGENT) && PYTHONPATH=. $(PY) -c "from zeg.evals.recognition import run_recognition; print(run_recognition().render())"

gate:
	cd $(AGENT) && PYTHONPATH=. $(PY) -c "from zeg.evals.gate import run_gate; print(run_gate().render())"

gaming:
	cd $(AGENT) && PYTHONPATH=. $(PY) -c "from zeg.evals.gaming import run_gaming; print(run_gaming().render())"

web:
	cd web && npm run dev

# The pitch deck. Edit SLIDES in tools/build_deck.py, run this, open deck.html.
# Arrow keys to move, N for speaker notes, F for fullscreen, print to PDF.
deck:
	$(PY) tools/build_deck.py deck.html

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

# ---- video review (services/vision, docs/12-video-review.md) ----------------------
# C++17 + OpenCV Haar cascades. OpenCV itself comes from the system: `brew install
# opencv` on a Mac, `sudo apt install libopencv-dev opencv-data` on Linux and the GB10 box, or
# services/vision/scripts/build_opencv.sh where neither is available.
vision-setup:
	$(PIP) install -q cmake ninja pybind11 av

vision:
	$(CMAKE) -S $(VISION) -B $(VISION_BUILD) -DCMAKE_BUILD_TYPE=Release \
		-DPython_EXECUTABLE=$(PY) $(if $(OPENCV_DIR),-DOpenCV_DIR=$(OPENCV_DIR),)
	$(CMAKE) --build $(VISION_BUILD) --parallel

test-vision: vision
	$(VISION_BUILD)/zeg_gaze_tests
	cd $(GATEWAY) && PYTHONPATH=.:$(CURDIR)/$(AGENT):$(CURDIR)/$(VISION_BUILD) $(PY) -m pytest -q tests/test_video_review.py
	cd $(AGENT) && $(PY) -m pytest -q tests/test_video_review.py

# The labelled clips are downloaded and generated, not committed. Real clips need PyAV
# (make vision-setup); the synthetic ones are built from the face stills in the tests.
STILLS := $(VISION)/tests/fixtures/stills
vision-eval-data: vision
	$(PY) $(VISION)/eval/fetch_clips.py
	mkdir -p $(VISION)/eval/synth
	$(VISION_BUILD)/zeg-gaze-synth --out $(VISION)/eval/synth \
		--frontal $$(ls $(STILLS)/frontal_*.jpg | paste -sd, -) \
		--profile $$(ls $(STILLS)/profile_*.jpg | paste -sd, -)

vision-eval:
	$(PY) $(VISION)/eval/eval.py --split test
