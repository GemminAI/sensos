# SensOS product entrypoints
#
# Requires a local .env (copy from .env.example and replace CHANGE_ME).
# Never commit .env. Never use template secrets in production.

COMPOSE := docker compose --env-file .env -f compose/docker-compose.yml

.PHONY: help up down config ps logs health build

help:
	@echo "SensOS product targets:"
	@echo "  make up           - bring up product stack (requires .env)"
	@echo "  make down         - stop stack"
	@echo "  make config       - validate compose file"
	@echo "  make ps           - show service status"
	@echo "  make logs         - follow gateway + observation logs"
	@echo "  make health       - curl gateway /healthz"
	@echo "  make build        - build product images"

up:
	@test -f .env || (echo "Missing .env — run: cp .env.example .env  then replace CHANGE_ME" >&2; exit 1)
	$(COMPOSE) up --build -d

down:
	@test -f .env || (echo "Missing .env — run: cp .env.example .env  then replace CHANGE_ME" >&2; exit 1)
	$(COMPOSE) down

config:
	@test -f .env || (echo "Missing .env — run: cp .env.example .env  then replace CHANGE_ME" >&2; exit 1)
	$(COMPOSE) config >/dev/null
	@echo "compose config OK"

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f gateway observation-runtime

health:
	curl -sf http://localhost:8080/healthz && echo

build:
	$(COMPOSE) build
