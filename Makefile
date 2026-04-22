.DEFAULT_GOAL := help

HOMESERVER   ?= http://localhost:8008
BASE_URL     ?= http://localhost:8080
ELEMENT_VER  ?= 1.12.15
ELEMENT_DIR  ?= /tmp/element-v$(ELEMENT_VER)
SYNAPSE_DATA ?= $(PWD)/synapse-data

# ── Python env ────────────────────────────────────────────────────────────────

.PHONY: install
install: ## Install deps + Playwright browser
	uv sync
	uv run playwright install chromium --with-deps

.PHONY: lint
lint: ## flake8 + mypy
	uv sync --group lint
	uv run flake8 framework/ tests/ --max-line-length=100
	uv run mypy framework/ --ignore-missing-imports

# ── Backend: Synapse ──────────────────────────────────────────────────────────

.PHONY: synapse-setup
synapse-setup: ## Pull Synapse image + generate config in ./synapse-data
	docker pull matrixdotorg/synapse:latest
	mkdir -p $(SYNAPSE_DATA)
	docker run --rm \
	  -v $(SYNAPSE_DATA):/data \
	  -e SYNAPSE_SERVER_NAME=localhost \
	  -e SYNAPSE_REPORT_STATS=no \
	  matrixdotorg/synapse:latest generate
	@# Enable open registration and disable rate limits for local testing
	@printf '\nenable_registration: true\nenable_registration_without_verification: true\n' >> $(SYNAPSE_DATA)/homeserver.yaml
	@printf 'rc_login:\n  address:\n    per_second: 100\n    burst_count: 1000\n  account:\n    per_second: 100\n    burst_count: 1000\n  failed_attempts:\n    per_second: 100\n    burst_count: 1000\n' >> $(SYNAPSE_DATA)/homeserver.yaml
	@echo "Synapse config generated in $(SYNAPSE_DATA)"

.PHONY: synapse-start
synapse-start: ## Start Synapse container (run synapse-setup first)
	docker run -d --name synapse-test \
	  -v $(SYNAPSE_DATA):/data \
	  -p 8008:8008 \
	  matrixdotorg/synapse:latest
	@echo "Synapse starting on http://localhost:8008"

.PHONY: synapse-stop
synapse-stop: ## Stop and remove Synapse container
	docker rm -f synapse-test 2>/dev/null || true

.PHONY: synapse-logs
synapse-logs: ## Tail Synapse logs
	docker logs -f synapse-test

# ── UI: Element Web ───────────────────────────────────────────────────────────

.PHONY: element-download
element-download: ## Download Element Web $(ELEMENT_VER) to /tmp
	curl -L -o /tmp/element.tar.gz \
	  https://github.com/element-hq/element-web/releases/download/v$(ELEMENT_VER)/element-v$(ELEMENT_VER).tar.gz
	tar xzf /tmp/element.tar.gz -C /tmp
	@# Point Element Web at local Synapse and disable E2EE verification prompt
	@printf '{\n  "default_server_config": {\n    "m.homeserver": {\n      "base_url": "http://localhost:8008",\n      "server_name": "localhost"\n    }\n  },\n  "disable_custom_urls": false,\n  "brand": "Element"\n}\n' > $(ELEMENT_DIR)/config.json
	@echo "Element Web $(ELEMENT_VER) ready in $(ELEMENT_DIR)"

.PHONY: element-start
element-start: ## Serve Element Web on :8080 (run element-download first)
	@pkill -f "http.server 8080" 2>/dev/null || true
	cd $(ELEMENT_DIR) && python3 -m http.server 8080 &>/tmp/element-http.log &
	@echo "Element Web serving on http://localhost:8080 (logs: /tmp/element-http.log)"

.PHONY: element-stop
element-stop: ## Stop Element Web HTTP server
	@pkill -f "http.server 8080" 2>/dev/null || echo "Not running"

# ── Composite ─────────────────────────────────────────────────────────────────

.PHONY: services-setup
services-setup: synapse-setup element-download ## Setup Synapse + Element Web from scratch

.PHONY: services-start
services-start: synapse-start element-start ## Start both Synapse and Element Web

.PHONY: services-stop
services-stop: synapse-stop element-stop ## Stop both services

# ── Tests ─────────────────────────────────────────────────────────────────────

.PHONY: test-api
test-api: ## API tests (requires Synapse on :8008)
	uv run pytest tests/api/ --homeserver $(HOMESERVER) -v

.PHONY: test-e2e
test-e2e: ## E2E tests (requires Synapse :8008 + Element :8080)
	uv run pytest tests/e2e/ --homeserver $(HOMESERVER) --base-url $(BASE_URL) -v

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
