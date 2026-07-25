# Semantic Annotator

Meaning attachment service for SensOS. Produces semantic annotations consumed
by HEXT Stream and HEKB projection.

Part of the product path:

```text
Observation → Semantic Annotator → HEKB → NVS Runtime → Applications
```

## Container

Uses the service-local `Dockerfile` (unchanged algorithm / API).
