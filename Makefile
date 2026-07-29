# GenieCommande — commandes de développement
# Usage : make <cible>

COMPOSE_PROD  = docker compose -f docker-compose.file2edi.yml
COMPOSE_DEV   = docker compose -f docker-compose.dev.yml
GIT           = git

.DEFAULT_GOAL := help

# ── Aide ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  GenieCommande — commandes disponibles"
	@echo ""
	@echo "  Dev local"
	@echo "    make dev          Démarrer l'API en hot-reload (port 8000)"
	@echo "    make dev-stop     Arrêter le stack de dev"
	@echo "    make dev-logs     Logs en temps réel (api)"
	@echo "    make frontend     Démarrer Vite dev server (port 5173, hot-reload UI)"
	@echo "    make install      Installer les dépendances frontend (npm ci)"
	@echo ""
	@echo "  Tests"
	@echo "    make test         Lancer tous les tests (dans le container dev)"
	@echo "    make test-fast    Tests rapides hors golden (dans le container dev)"
	@echo ""
	@echo "  Production (VM)"
	@echo "    make prod-up      Démarrer la prod"
	@echo "    make prod-down    Arrêter la prod"
	@echo "    make prod-build   Rebuild l'image de prod"
	@echo "    make prod-logs    Logs en temps réel (prod)"
	@echo "    make prod-status  Statut des containers de prod"
	@echo "    make deploy       Rebuild + redémarrer la prod (full deploy)"
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

install:
	cd frontend && npm ci

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	$(COMPOSE_DEV) run --rm api python -m pytest tests/ --tb=short -q

test-fast:
	$(COMPOSE_DEV) run --rm api python -m pytest tests/ -k "not golden" --tb=short -q

# ── Production ────────────────────────────────────────────────────────────────

prod-up:
	$(COMPOSE_PROD) up -d

prod-down:
	$(COMPOSE_PROD) down

prod-build:
	$(COMPOSE_PROD) build file2edi

prod-logs:
	$(COMPOSE_PROD) logs -f file2edi

prod-status:
	$(COMPOSE_PROD) ps

deploy: prod-build prod-up
	@echo "Deploy terminé."

# ── Git ───────────────────────────────────────────────────────────────────────

sync-branches:
	$(GIT) checkout staging && $(GIT) merge main --ff-only
	$(GIT) checkout dev     && $(GIT) merge main --ff-only
	$(GIT) checkout main
	$(GIT) push origin main staging dev
	@echo "Branches staging et dev synchronisées."

.PHONY: help dev dev-stop dev-logs frontend install test test-fast \
        prod-up prod-down prod-build prod-logs prod-status deploy sync-branches
