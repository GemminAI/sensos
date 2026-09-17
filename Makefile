# SensOS product entrypoints
#
# Requires a local .env (copy from .env.example and replace CHANGE_ME).
# Never commit .env. Never use template secrets in production.

COMPOSE := docker compose --env-file .env -f compose/docker-compose.yml

.PHONY: help up down config ps logs health build hekb-devkeys

help:
	@echo "SensOS product targets:"
	@echo "  make up           - bring up product stack (requires .env)"
	@echo "  make down         - stop stack"
	@echo "  make config       - validate compose file"
	@echo "  make ps           - show service status"
	@echo "  make logs         - follow gateway + observation logs"
	@echo "  make health       - curl gateway /healthz and hekb-vnext /health"
	@echo "  make build        - build product images"
	@echo "  make hekb-devkeys - one-time dev-only P-256 keypair for hekb-vnext"
	@echo "                      (POST /experience's X-Audit-Signature gate;"
	@echo "                      never the real Secure Enclave key)"

hekb-devkeys:
	@test -f ../hekb-vnext/tools/dev_audit_signer.py || \
		(echo "../hekb-vnext not found as a sibling clone of this repo" >&2; exit 1)
	python3 ../hekb-vnext/tools/dev_audit_signer.py keygen ../hekb-vnext/devkeys
	@echo "Dev-only P-256 keypair written to ../hekb-vnext/devkeys/"
	@echo "(HEKB_AUDIT_PUBLIC_KEY_PATH in .env.example already points at the mounted public key)"

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
	curl -sf http://localhost:8300/health && echo

build:
	$(COMPOSE) build
