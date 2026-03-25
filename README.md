# ECU Analytics Platform

Professional-grade engine telemetry analytics dashboard with automated diagnostic rule-sets and Gemini-powered tuning assistance.

## Features
- **3-Tier Diagnostic Hierarchy**: Synchronized visualizations for Throttle, MAP (Load), and MAF (Airflow).
- **Automated Fault Detection**: Rule-based engine to identify rich burn, load inconsistencies, and efficiency gaps.
- **High Resolution Analysis**: Data binned into 100 RPM increments for precise curve visualization.
- **Interactive AI Chat**: Physics-based diagnostic assistant integrated directly with telemetry charts.
- **Universal Log Support**: Fuzzy-keyword matching for Haltech, Link, Motec, and other generic ECU exports.

## Project Structure
- `/backend`: FastAPI service for data processing and AI integration.
- `/frontend`: Next.js React dashboard using Recharts for visualization.

## Setup Instructions

### Backend (Python 3.10+)
1. Navigate to `backend/`.
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the API server:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

### Frontend (Node.js 18+)
1. Navigate to `frontend/`.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
4. Access the dashboard at `http://localhost:3000`.

## Sharing & Collaboration
This project is configured for Git-based collaboration.
- Ensure large log files are kept in the ignored directories.
- Always provide your own Gemini API key via the UI input for the AI features to function.
