# SensOS product entrypoints

COMPOSE := docker compose -f compose/docker-compose.yml

.PHONY: help up down config ps logs health build

help:
	@echo "SensOS product targets:"
	@echo "  make up           - bring up product stack"
	@echo "  make down         - stop stack"
	@echo "  make config       - validate compose file"
	@echo "  make ps           - show service status"
	@echo "  make logs         - follow gateway + observation logs"
	@echo "  make health       - curl gateway /healthz"
	@echo "  make build        - build product images"

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

config:
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
