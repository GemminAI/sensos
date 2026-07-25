# Dashboard

Operator presentation surface for SensOS.

- This service is the **release unit** (container) for the product dashboard.
- Shared UI building blocks live in `packages/runtime-ui` (`@nvs/runtime-ui`).

The current image serves a production-oriented operator shell with edge health
links. Rich interactive views can be composed on top of `runtime-ui` without
changing Observation / Annotator / Runtime algorithms.
