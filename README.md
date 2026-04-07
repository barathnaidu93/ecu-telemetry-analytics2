# ECU Telemetry Analytics Platform

Professional-grade ECU diagnostic and calibration platform. Ingest high-fidelity telemetry logs (CSV/BIN) from any ECU export tool, run automated physics-based diagnostics, visualize multi-signal time-series data, and query a Gemini-powered Lead Calibration Engineer for targeted fault analysis.

---

## Features

| Capability | Detail |
|------------|--------|
| **Universal Log Ingestion** | Fuzzy-keyword alias mapping handles MHD, COBB, Haltech, Link, Motec, AEM, and generic CSV exports without configuration |
| **Hardened Normalization** | Multi-signal heuristic unit detection (kPa/BAR/PSI for MAP; AFR/Lambda; percent/voltage/fraction for TPS) with confidence scoring |
| **Anomaly Logging** | Pre-clamp anomaly detection records out-of-range sensor readings before they are corrected |
| **Physics-Based Diagnostics** | Specified vs. Actual correlation rules: Boost Leak (MAP vs. Boost Target), HPFP Rail Pressure Sag, Rich Burn detection |
| **Multi-Chart Dashboard** | Master Plot, MAF, Throttle/MAP, Fueling (AFR + Lambda), Ignition + Knock, Fuel Trims (STFT/LTFT) — all time-synced |
| **AFR Heatmap** | Engineering-grade RPM × Load fuel map with WOT-only filtering and noise rejection |
| **Global Calibration Map** | Merge multiple logs into a single aggregated dataset for cross-scenario fuel map analysis |
| **AI Tuning Agent** | Gemini-powered chat with structured responses: Status → Observation → Physics → Remedy |
| **Telemetry Pin System** | Click two points on any chart to get precise delta analysis across all signals |
| **Data Traceability** | Original signal statistics (pre-conversion) stored in DataFrame metadata for audit trails |

---

## Project Structure

```
project-root/
├── backend/
│   ├── main.py                  # FastAPI app — upload, diagnostics, heatmap, AI chat
│   ├── merge_logs.py            # Batch CSV merge for Global Calibration Map
│   ├── requirements.txt
│   ├── core/
│   │   ├── ingestion.py         # Pipeline orchestrator: IO → clean → normalize → validate
│   │   └── mapping.py           # Alias database + fuzzy column mapper (11 standard signals)
│   ├── utils/
│   │   ├── io_utils.py          # Robust CSV reader (two-pass header detection)
│   │   ├── time_utils.py        # Time-axis detection, ms→s normalization, dt computation
│   │   ├── unit_utils.py        # V2 unit normalization engine with confidence scoring
│   │   ├── validation_utils.py  # Physical sanity checks (RPM/AFR/MAP/TPS ranges)
│   │   ├── binning_utils.py     # RPM/Load binning for heatmap generation
│   │   └── type_utils.py        # JSON serialization helpers
│   ├── models/
│   │   └── metadata.py          # Sampling rate + unit traceability metadata builder
│   ├── tests/                   # Test suite (run standalone — no pytest required)
│   │   ├── test_unit_sync.py
│   │   ├── test_normalization_v2.py
│   │   └── test_dirty_ingestion.py
│   ├── test_imports.py          # Quick dependency sanity check
│   ├── verify_fix.py            # Manual pipeline verification script
│   └── verify_unit_pipeline.py  # Unit normalization pipeline verification
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Main dashboard (charts, heatmap, AI chat)
│   │   ├── layout.tsx           # Root layout (Inter font, metadata)
│   │   └── globals.css          # Base styles, font variables, scrollbar
│   └── package.json
│
├── csv_logs/                    # Place your telemetry CSV files here for Global Heatmap
├── EngineFaultDB_Final.csv      # Reference engine fault database
└── README.md
```

---

## Setup

### Backend (Python 3.10+)

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Start the API server (port 8899)
uvicorn main:app --reload --port 8899
```

> **Note:** The API runs on **port 8899** by default. The frontend is preconfigured to connect to `http://localhost:8899`.

### Frontend (Node.js 18+)

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

---

## Usage

### Single Log Analysis (Diagnostic Tab)

1. Click **"Choose File"** and select a `.csv` or `.bin` telemetry log
2. Click **"Analyze"** — the pipeline runs automatically:
   - Header detection → alias mapping → unit normalization → validation
3. Use the chart selector icons to enable/disable signal panels
4. Click any chart point to **pin it** (click a second point to see deltas)
5. Enter your **Gemini API key** in the chat header and ask questions about the data

### Global Calibration Map (Global Tab)

1. First, run `merge_logs.py` to combine all CSVs in `csv_logs/`:
   ```bash
   cd backend
   python merge_logs.py csv_logs/
   ```
2. Upload the generated `csv_logs/merged_calibration_data.csv` in the Global tab

### Running Tests

```bash
cd backend
source venv/Scripts/activate   # or venv/bin/activate

python tests/test_unit_sync.py         # Unit normalization (10 assertions)
python tests/test_normalization_v2.py  # Edge cases + detection functions
python tests/test_dirty_ingestion.py   # Full pipeline integration test
```

---

## Supported ECU Log Formats

The alias mapper recognizes signals from the following tools without any configuration:

| ECU / Tool | Tested Signals |
|------------|---------------|
| MHD Flasher (BMW S58 / N55 / B58) | nmot, lam, boost, tps, dwout, zwout |
| COBB Accessport (VW/Audi EA888) | rpm, manifold pressure, afr, timing |
| Haltech | engine rpm, map sensor, wideband O2 |
| Link ECU | rpm, tps, afr, ign angle |
| Generic OBD2 CSV | RPM, Throttle, MAP, MAF, Lambda |

---

## Environment & API Keys

- **Gemini API Key:** Enter via the UI chat input. Never hardcode in source.
- **No `.env` file required** — the backend reads the key from the request payload.
- Log files (`.csv`, `.bin`) are excluded from git via `.gitignore`. Keep large datasets in `csv_logs/`.

---

## Architecture Notes

- **Idempotency:** The pipeline sets `df.attrs["_units_normalized"] = True` after normalization. Re-processing the same DataFrame is a no-op.
- **Traceability:** Pre-conversion signal statistics (mean, median, max) are stored in `df.attrs["original_units"]` for downstream audit.
- **Concurrency:** The backend uses a global in-memory store (single-user design). For multi-user deployment, replace with Redis or database-backed session storage.
- **Collision Safety:** If two source columns both match the same standard signal (e.g., two boost columns), the first match wins and a warning is logged.
