# Security Policy

## Supported versions

Security fixes are applied to the currently supported SensOS release train
published from this repository (`main` and the latest tagged release).

## Reporting a vulnerability

Do **not** open a public GitHub issue for security vulnerabilities.

Please report suspected vulnerabilities privately to:

- **security@gemmina.ai** (preferred)
- Or via your Gemmina Intelligence account team if under a commercial contract

Include:

1. Affected component / service name
2. Version or commit SHA
3. Reproduction steps or proof of concept (non-destructive)
4. Impact assessment if known

We will acknowledge receipt within 3 business days and provide a status update
within 10 business days.

## Scope

In scope:

- `services/*` product containers and APIs
- `integrations/*` SensOS-side adapters
- Authentication, authorization, and secret handling in this repository
- Container images built from this repository

Out of scope:

- External OSS dependencies (HEKB, HEXT SDK, MCP servers) — report upstream
- Research Vault artifacts
- Third-party LLM provider outages

## GitHub Secret Scanning

This repository is intended to be protected by:

- Secret Scanning
- Push Protection
- Dependabot
- CodeQL

Contributors must never commit credentials or production secrets.

## Hardening expectations

- No secrets in git; use environment variables or a secret manager
- Prefer least-privilege service accounts between containers
- Gateway is the only public edge in production deployments
- Proprietary NVS-Kernel remains outside this repository; only ABI/interfaces ship here

## Development templates

`.env.example` and placeholder entries in `configs/auth.yaml` are **development templates only**.

- Copy `.env.example` → `.env` for local Compose
- Replace every `CHANGE_ME` / placeholder with secrets you generate
- Never commit `.env`
- Never deploy template values to production
- Production secrets must come from a secret manager or the deployment environment

If `NVS_JWT_SECRET` is still a template value such as `CHANGE_ME`, NVS Runtime refuses to start.

## Security Philosophy

SensOS is designed so that production secrets never live inside the repository.

All production credentials must be supplied externally through the deployment environment, secret managers, or orchestration systems.
