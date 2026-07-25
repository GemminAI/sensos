import type { Capabilities } from '../models/types'

const LAYER3 = [
  { name: 'Forecast', rfc: 'RFC-NVS30', stub: 'nvs_forecast_transition' },
  { name: 'Integrity', rfc: 'RFC-NVS31', stub: 'nvs_check_integrity' },
  { name: 'Alignment', rfc: 'RFC-NVS32', stub: 'nvs_get_alignment_profile' },
  { name: 'Boundary', rfc: 'RFC-NVS33', stub: 'nvs_check_boundary_status' },
]

interface Props {
  capabilities: Capabilities | null
}

export function CapabilitiesView({ capabilities }: Props) {
  const stubs = new Set(capabilities?.layer3_stubs ?? [])
  const tools = new Set(capabilities?.mcp_tools ?? [])

  return (
    <section className="panel capabilities">
      <h2>Capabilities</h2>
      {capabilities && (
        <p className="muted">
          {capabilities.service} {capabilities.version} · {capabilities.rfc}
        </p>
      )}
      <ul className="layer3-list">
        {LAYER3.map((l) => {
          const listed = stubs.has(l.stub) || tools.has(l.stub)
          return (
            <li key={l.name} className="layer3-card placeholder">
              <strong>{l.name}</strong>
              <span className="not-implemented">NOT_IMPLEMENTED</span>
              <span className="rfc-ref">{l.rfc}</span>
              {!listed && <span className="muted">(not registered)</span>}
            </li>
          )
        })}
      </ul>
      <p className="muted small">Layer 3 panels are placeholder only per RFC-NVS43 §7.</p>
    </section>
  )
}
