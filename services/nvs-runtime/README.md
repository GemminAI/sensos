# NVS Runtime

Application / session plane for SensOS: agents, events, MCP, and the
in-process `KernelGateway` used to reach Observation Runtime / NVS-Kernel.

## Container

```bash
docker build -t sensos/nvs-runtime:latest -f Dockerfile .
```

## Notes

- Gateway **edge** reverse-proxy lives in `services/gateway/` (separate container).
- In-process kernel client remains at `runtime/gateway/` (unchanged).
