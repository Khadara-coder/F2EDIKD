# GenieCommande — commandes de développement
# Usage : make <cible>

COMPOSE_QUALITY = docker compose -f docker-compose.file2edi.yml
COMPOSE_PROD    = docker compose -f docker-compose.prod.yml
COMPOSE_DEV     = docker compose -f docker-compose.dev.yml
GIT             = git

.DEFAULT_GOAL := help

# Guard: abort if not on main branch
.PHONY: _require-main
_require-main:
	@branch=$$(git rev-parse --abbrev-ref HEAD); \
	if [ "$$branch" != "main" ]; then \
	  echo "ERROR: prod deploy requires branch 'main' (currently on '$$branch')."; \
	  echo "       Run: git checkout main && git pull"; \
	  exit 1; \
	fi

# ── Aide ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  GenieCommande — commandes disponibles"
	@echo ""
	@echo "  Dev local"
	@echo "    make dev            Démarrer l'API en hot-reload (port 8000)"
	@echo "    make dev-stop       Arrêter le stack de dev"
	@echo "    make dev-logs       Logs en temps réel (api)"
	@echo "    make frontend       Démarrer Vite dev server (port 5173, hot-reload UI)"
	@echo "    make install        Installer les dépendances frontend (npm ci)"
	@echo ""
	@echo "  Tests"
	@echo "    make test           Backend pytest complet (dans le container dev)"
	@echo "    make test-fast      Backend pytest hors golden (dans le container dev)"
	@echo "    make test-frontend  Vitest unit tests (frontend, jsdom)"
	@echo "    make test-e2e       Playwright E2E mockés (frontend, sans backend)"
	@echo "    make test-e2e-smoke Playwright smoke contre le backend réel (F2EDI_USER/PASSWORD requis)"
	@echo "    make test-all       Backend pytest + frontend Vitest + E2E mockés"
	@echo ""
	@echo "  Quality (adv.bosch-homecomfort.com — port 8080)"
	@echo "    make quality-up     Démarrer le stack quality"
	@echo "    make quality-down   Arrêter le stack quality"
	@echo "    make quality-build  Rebuild l'image quality"
	@echo "    make quality-logs   Logs en temps réel (quality)"
	@echo "    make quality-status Statut des containers quality"
	@echo "    make deploy-quality Rebuild + redémarrer quality"
	@echo ""
	@echo "  Production (port 8090) — BRANCH main OBLIGATOIRE"
	@echo "    make prod-up        Démarrer la prod"
	@echo "    make prod-down      Arrêter la prod"
	@echo "    make prod-build     Rebuild l'image de prod (exige main)"
	@echo "    make prod-logs      Logs en temps réel (prod)"
	@echo "    make prod-status    Statut des containers de prod"
	@echo "    make deploy         git pull main + rebuild + redémarrer prod"
	@echo ""
	@echo "  Git"
	@echo "    make sync-branches  Fast-forward staging et dev sur main"
	@echo ""

# ── Dev local ────────────────────────────────────────────────────────────────

dev:
	@cp -n .env.local.example .env.local 2>/dev/null && \
	  echo "⚠  .env.local créé depuis .env.local.example — renseigner DATABRICKS_TOKEN" || true
	$(COMPOSE_DEV) up --build

dev-stop:
	$(COMPOSE_DEV) down

dev-logs:
	$(COMPOSE_DEV) logs -f api

frontend:
	cd frontend && npm run dev

graph:
	powershell -ExecutionPolicy Bypass -File scripts/graphify_project.ps1

graph-update:
	powershell -ExecutionPolicy Bypass -File scripts/graphify_project.ps1 -Update

install:
	cd frontend && npm ci

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	$(COMPOSE_DEV) run --rm api python -m pytest tests/ --tb=short -q

test-fast:
	$(COMPOSE_DEV) run --rm api python -m pytest tests/ -k "not golden" --tb=short -q

test-frontend:
	cd frontend && npm run test:unit

test-e2e:
	cd frontend && npm run test:e2e -- --project=chromium-mocked

test-e2e-smoke:
	cd frontend && npm run test:e2e -- --project=chromium-smoke

test-all: test-fast test-frontend test-e2e
	@echo "Tests backend + frontend + E2E mockés terminés."

# ── Quality ───────────────────────────────────────────────────────────────────

quality-up:
	$(COMPOSE_QUALITY) up -d

quality-down:
	$(COMPOSE_QUALITY) down

quality-build:
	$(COMPOSE_QUALITY) build file2edi

quality-logs:
	$(COMPOSE_QUALITY) logs -f file2edi

quality-status:
	$(COMPOSE_QUALITY) ps

deploy-quality: quality-build quality-up
	@echo "Deploy quality terminé."

# ── Production (main branch only) ────────────────────────────────────────────

prod-build: _require-main
	$(COMPOSE_PROD) build file2edi

prod-up: _require-main
	$(COMPOSE_PROD) up -d

prod-down:
	$(COMPOSE_PROD) down

prod-logs:
	$(COMPOSE_PROD) logs -f file2edi

prod-status:
	$(COMPOSE_PROD) ps

deploy: _require-main
	$(GIT) pull origin main
	$(COMPOSE_PROD) build file2edi
	$(COMPOSE_PROD) up -d
	@echo "Deploy prod terminé depuis main."

# ── Git ───────────────────────────────────────────────────────────────────────

sync-branches:
	$(GIT) checkout staging && $(GIT) merge main --ff-only
	$(GIT) checkout dev     && $(GIT) merge main --ff-only
	$(GIT) checkout main
	$(GIT) push origin main staging dev
	@echo "Branches staging et dev synchronisées."

.PHONY: help dev dev-stop dev-logs frontend graph graph-update install \
        test test-fast test-frontend test-e2e test-e2e-smoke test-all \
        quality-up quality-down quality-build quality-logs quality-status deploy-quality \
        prod-up prod-down prod-build prod-logs prod-status deploy \
        sync-branches _require-main
