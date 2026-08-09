# Every target runs from the repo root. The frontend lives five directories
# down, so each UI target does its own `cd` rather than making you remember it.
#
# `make check` is the full gate. Keep it that way: README and CLAUDE.md point
# here instead of restating the command list, so they cannot drift from it.

UI := src/ios_loc/web/ui
HOST ?= 127.0.0.1

.DEFAULT_GOAL := help
.PHONY: help install check test test-py test-ui lint lint-py lint-ui fmt \
        build build-ui gui dev schema types clean

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install Python deps (CLI only — the GUI also needs `make build`)
	uv sync

check: lint-py test-py test-ui lint-ui build-ui  ## The full gate: lint + test + build, both languages

# --- Python ------------------------------------------------------------------

test-py:  ## Python suite (~2s, no device or network needed)
	uv run pytest -q

lint-py:  ## ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

fmt:  ## Apply ruff's formatting and autofixes
	uv run ruff check --fix .
	uv run ruff format .

schema:  ## Regenerate the OpenAPI schema the frontend types from
	uv run python scripts/export_openapi.py

# --- Frontend ----------------------------------------------------------------

test-ui:  ## Frontend pure-logic tests (no DOM — see CLAUDE.md)
	cd $(UI) && pnpm test run

lint-ui:  ## oxlint (two expected warnings in vendored shadcn files)
	cd $(UI) && pnpm lint

build-ui:  ## Build the bundle into web/static/ — also the frontend typecheck
	cd $(UI) && pnpm install --frozen-lockfile && pnpm build

types:  ## Regenerate src/api/schema.d.ts from api-schema.json
	cd $(UI) && pnpm gen:api

# --- Running -----------------------------------------------------------------

# `ios-loc gui` serves the built bundle, never the source, so build first.
# Vite is fast and a no-op when nothing changed; this is what keeps you from
# debugging a UI change that was never built.
gui: build-ui  ## Serve the GUI from a freshly built bundle (HOST=0.0.0.0 make gui to expose it)
	uv run ios-loc gui --host $(HOST)

dev:  ## Vite on 5173 (proxying to uvicorn) + the API on 8765, together
	uv run ios-loc gui & \
	cd $(UI) && pnpm dev; \
	kill %1 2>/dev/null || true

# --- Aliases -----------------------------------------------------------------

test: test-py test-ui  ## Both test suites
lint: lint-py lint-ui  ## Both linters
build: build-ui        ## Build the GUI bundle

clean:  ## Remove the built bundle and Python caches
	rm -rf src/ios_loc/web/static
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache
