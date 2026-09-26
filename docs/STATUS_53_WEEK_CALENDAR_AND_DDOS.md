# Standard: 53-Week Uptime Calendar, DDoS Incident States & Synthetic JSON Status

- **Status Authority**: `wellmanifest/status`
- **Specification Version**: `1.1.0`
- **Owner Entity**: Tomasz Sapletta Prototypowanie.pl (NIP: 5881918662, REGON: 220665410)
- **Reference Implementations**: `status.clonerd.com`, `clonerd-com/status-clonerd-com`

---

## 1. Architectural Purpose

A service status page serves two distinct audiences:
1. **Human Operators & End Users**: Need immediate visual clarity regarding real-time availability, past incidents, and annual service stability.
2. **Autonomous Supervisors (e.g. Koru, Bastion Planes, Synthetic Probers)**: Require deterministic, machine-readable JSON status schemas (`/status.json`, `/healthz`) to make routing, failover, and automated remediation decisions.

Traditional status models collapse into a binary "UP" or "DOWN", which fails catastrophically under modern distributed DDoS attacks or dynamic traffic shifting. When edge ingress actively shunts an attacker vector into a tarpit/honeypot while keeping authenticated user workloads operational, marking the entire cluster "DOWN" triggers false-alarm cascades and panics upstream dependents.

---

## 2. 53-Week Annual Uptime Calendar Specification

The annual uptime calendar visualizes a rolling 371-day window organized into a 53-column by 7-row matrix (GitHub-style calendar grid).

### 2.1 Calendar Metrics & Bucketing
- **Total Days**: Exactly 371 days (53 full weeks $\times$ 7 days/week).
- **Day Buckets**: Each day represents 00:00:00 to 23:59:59 UTC.
- **Color Codes & Health Thresholds**:
  - `operational` (`#10b981` / Emerald Green): 100.0% availability, 0 unresolved critical incidents.
  - `degraded` (`#f59e0b` / Amber): 95.0% - 99.9% availability, elevated latency, or scheduled maintenance.
  - `ddos_mitigation` (`#8b5cf6` / Violet): Active volumetric or L7 attack mitigation; legitimate user traffic preserved via honeypot/tarpit vector shunting.
  - `major_outage` (`#ef4444` / Crimson Red): < 95.0% availability or complete unavailability of primary workloads.

### 2.2 Calendar JSON Structure
```json
{
  "calendar": [
    {
      "date": "2026-09-26",
      "status": "operational",
      "uptime_percentage": 100.0,
      "incidents_count": 0,
      "latency_p95_ms": 28.4
    }
  ]
}
```

---

## 3. Autonomous Remediation & DDoS Incident States

### 3.1 Status Vocabularies
A system state is classified across five explicit levels:
1. `operational`: All systems nominal. All synthetic health probes return `200 OK` within latency SLAs ($p95 < 200\text{ms}$).
2. `degraded`: One or more non-critical subsystems experiencing elevated latencies or reduced redundancy.
3. `ddos_mitigation`: Active L3/L4 volumetric flood or L7 HTTP flood detected. Autonomous defense (e.g., Koru controller) has shunted the attack vector into rate-limiting honeypots or tarpits. Legitimate user traffic remains routed to production twins.
4. `maintenance`: Pre-announced operational intervention, rolling container upgrades, or twin snapshot WAL synchronization.
5. `major_outage`: Primary user-facing core services unreachable or returning sustained $>5xx$ responses.

### 3.2 Dynamic Vector Shifting Invariant
When edge reverse proxies (such as Caddy / Envoy) dynamically route malicious IPs or abusive patterns to synthetic response delays (tarpits) or isolated quarantine twins:
- The component status reports `ddos_mitigation`.
- Upstream load balancers and external heartbeat monitors MUST NOT mark the entire origin node offline if synthetic verification of authenticated endpoints succeeds.

---

## 4. Machine-Readable Endpoints Contract

### 4.1 `/status.json` Standard Schema
All adhering status servers MUST expose `/status.json` with cache-control `max-age=10, must-revalidate` and `X-Robots-Tag: noindex, noarchive`.

```json
{
  "schema": "wellmanifest.status/v1",
  "generated_at": "2026-09-26T12:00:00Z",
  "system_status": "operational",
  "owner": "Tomasz Sapletta Prototypowanie.pl NIP: 5881918662, REGON: 220665410",
  "metrics": {
    "uptime_365d": 99.98,
    "uptime_90d": 100.0,
    "uptime_30d": 100.0,
    "current_latency_ms": {
      "p50": 18.2,
      "p95": 32.5,
      "p99": 64.1
    }
  },
  "components": [
    {
      "id": "edge_ingress",
      "name": "Edge Ingress & TLS Termination (Caddy)",
      "status": "operational",
      "latency_ms": 12.0
    },
    {
      "id": "api_gateway",
      "name": "API Services & Fleet Gateway",
      "status": "operational",
      "latency_ms": 24.5
    },
    {
      "id": "twin_virtualization",
      "name": "Native Twin Virtualization & Isolation Runtime",
      "status": "operational",
      "latency_ms": 18.0
    },
    {
      "id": "billing_licensing",
      "name": "Billing, Cryptography & DRM Node Licensing",
      "status": "operational",
      "latency_ms": 31.0
    },
    {
      "id": "cluster_telemetry",
      "name": "Zero-Trust Cluster Telemetry & Bastion Plane",
      "status": "operational",
      "latency_ms": 15.0
    }
  ],
  "active_incidents": []
}
```

### 4.2 Lightweight Probes (`/healthz` and `/livez`)
- `/healthz`: Shallow daemon responsiveness check. Returns `200 OK` with `{"status": "ok"}`.
- `/livez`: Deep synthetic verification check. Probes local loopback dependencies (storage CoW, database connection pool, cryptographic keyrings) before returning `200 OK`.
