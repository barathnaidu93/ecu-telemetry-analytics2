# ECU Telemetry Analytics — Frontend

## Project Context

This is the Next.js 16 frontend for the ECU Telemetry Analytics platform —
a professional-grade engine diagnostic and calibration dashboard.

## Architecture

- **Framework:** Next.js 16 / React 19 (App Router)
- **Charts:** Recharts (LineChart, ScatterChart, heatmap tables)
- **AI Chat:** Connects to `/chat` endpoint on the FastAPI backend
- **Styling:** Inline styles + globals.css (Inter font via next/font/google)
- **API:** Backend expected at `http://localhost:8889` (FastAPI, port 8889)

## Key Files

| File | Purpose |
|------|---------|
| `app/page.tsx` | Main dashboard (1500+ lines, all UI logic) |
| `app/layout.tsx` | Root layout — font loading (Inter, Geist), metadata |
| `app/globals.css` | Base resets, font-family, scrollbar theming |

## Data Flow

1. User uploads `.csv` or `.bin` via the Diagnostic tab
2. POST to `/upload` → backend ingestion pipeline runs
3. `resultData` state populated with: `chart_master`, `chart_rpm`, `chart_fueling`, `chart_ignition`, `chart_fuel_trims`, `afr_heatmap`, `diagnostics`, `column_stats`, `metadata`
4. Charts render conditionally based on which sensors are detected
5. Clicking a chart point auto-fills the AI chat with a contextual prompt

## Tab Structure

- **Diagnostic Tab** — Individual log analysis (Master Plot, MAF, Throttle/MAP, Fueling, Ignition, Fuel Trims, AFR Heatmap)
- **Global Heatmap Tab** — Upload a merged CSV to render a cross-scenario calibration map

## Development

```bash
npm install
npm run dev   # http://localhost:3000
```

Backend must be running at port 8899 for uploads and chat to work.
