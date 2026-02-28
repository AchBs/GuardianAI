"""
main.py
=======
Guardian AI - FastAPI Application

Endpoints:
  GET  /              -> Serve the real-time dashboard (dashboard.html)
  GET  /api/simulate  -> Run full simulation and return JSON results
  GET  /api/metrics   -> Return latest summary metrics (JSON)
  WS   /ws/simulate   -> WebSocket: stream real-time data points to dashboard

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import numpy as np
import pandas as pd

from guardian_ai.simulator  import TunisianCitySimulator
from guardian_ai.detector   import FDIDetector
from guardian_ai.optimizer  import SmartCityOptimizer
from guardian_ai.security   import GuardianSecurityLayer


# ── App initialisation ────────────────────────────────────────────────────────
app = FastAPI(
    title       = "Guardian AI - Tunisia Smart Cities",
    description = "Real-time FDI detection & energy optimisation for public infrastructure",
    version     = "1.0.0",
)

STATIC_DIR = Path(__file__).parent / "static"

# ── Cached simulation state (shared across WS connections) ───────────────────
_cached_df: Optional[pd.DataFrame] = None
_cached_metrics: Optional[dict]    = None
_security = GuardianSecurityLayer()


def _run_pipeline(
    attack_probability: float = 0.04,
    seed: int = 42,
) -> tuple[pd.DataFrame, dict]:
    """
    Execute the full Guardian AI pipeline:
      Simulate -> Detect -> Correct -> Optimise
    Returns (processed_df, metrics_dict)
    """
    sim       = TunisianCitySimulator(seed=seed)
    detector  = FDIDetector()
    optimizer = SmartCityOptimizer()

    # 1. Generate clean training data (different seed = historical reference period)
    clean_df = sim.generate_normal_data(hours=48)   # 2-day clean baseline
    detector.fit(clean_df)                           # train on clean data

    # 2. Generate 24h deployment data
    df = sim.generate_normal_data(hours=24)

    # 3. Inject FDI attacks
    df = sim.inject_fdi_attacks(df, attack_probability=attack_probability)

    # 4. Detect anomalies (hybrid ensemble using fitted clean baseline)
    df = detector.detect(df)

    # 4. Correct corrupted readings
    df = detector.correct_data(df)

    # 5. Optimise energy/water allocation
    df = optimizer.optimize(df)

    # 6. Compute summary
    metrics = optimizer.compute_metrics(df)
    metrics.update(detector.compute_detection_metrics(df))

    return df, metrics


def _df_to_json_list(df: pd.DataFrame) -> list:
    """Convert DataFrame to a JSON-serialisable list of dicts."""
    records = []
    for i, row in df.iterrows():
        records.append({
            "minute"               : int(i),
            "timestamp"            : row["timestamp"].strftime("%H:%M"),
            "lighting_raw"         : round(float(row["lighting_kw"]),                                   2),
            "lighting_original"    : round(float(row.get("original_lighting", row["lighting_kw"])),   2),
            "lighting_corrected"   : round(float(row["lighting_corrected"]),                          2),
            "lighting_optimized"   : round(float(row["lighting_optimized"]),                          2),
            "water_raw"            : round(float(row["water_lpm"]),                                   2),
            "water_original"       : round(float(row.get("original_water",   row["water_lpm"])),      2),
            "water_corrected"      : round(float(row["water_corrected"]),                             2),
            "water_optimized"      : round(float(row["water_optimized"]),                             2),
            "is_attack"            : bool(row["is_attack"]),
            "detected_attack"      : bool(row["detected_attack"]),
            "attack_type"          : str(row["attack_type"]),
            "detection_reason"     : str(row.get("detection_reason", "")),
            "anomaly_score"        : round(float(row.get("anomaly_score", 0)), 2),
            "savings_pct"          : round(float(row["cumulative_savings_pct"]), 1),
            "savings_tnd"          : round(float(row["savings_tnd"]),         4),
        })
    return records


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
async def serve_dashboard():
    """Serve the real-time Guardian AI dashboard."""
    html_file = STATIC_DIR / "dashboard.html"
    if not html_file.exists():
        return HTMLResponse("<h1>dashboard.html not found</h1>", status_code=404)
    return HTMLResponse(html_file.read_text(encoding="utf-8"))


@app.get("/api/simulate", tags=["API"])
async def api_simulate(
    attack_prob: float = Query(0.04,  description="Per-minute attack probability (0-1)"),
    seed:        int   = Query(42,    description="Random seed for reproducibility"),
):
    """
    Run full simulation pipeline and return all data points + metrics.
    Useful for offline analysis or notebook ingestion.
    """
    global _cached_df, _cached_metrics
    df, metrics = _run_pipeline(attack_probability=attack_prob, seed=seed)
    _cached_df      = df
    _cached_metrics = metrics
    return JSONResponse({
        "metrics": metrics,
        "data"   : _df_to_json_list(df),
    })


@app.get("/api/metrics", tags=["API"])
async def api_metrics():
    """Return latest cached metrics (or run default simulation if none cached)."""
    global _cached_df, _cached_metrics
    if _cached_metrics is None:
        _cached_df, _cached_metrics = _run_pipeline()
    return JSONResponse(_cached_metrics)


@app.get("/api/security/audit", tags=["Security"])
async def api_audit():
    """Return the last 50 security audit log entries."""
    return JSONResponse({
        "summary" : _security.audit.get_summary(),
        "recent"  : _security.audit.get_recent(50),
    })


@app.websocket("/ws/simulate")
async def ws_simulate(
    websocket: WebSocket,
    attack_prob: float = Query(0.04),
    seed:        int   = Query(42),
    speed_ms:    int   = Query(40,  description="Delay between data points in ms"),
):
    """
    WebSocket endpoint that streams simulation data in real-time.

    Protocol:
      - Server sends JSON objects one per data point.
      - First message: {"type": "init", "metrics": {...}, "total": N}
      - Data messages: {"type": "data", ...fields...}
      - Last message:  {"type": "done", "metrics": {...}}
    """
    await websocket.accept()
    try:
        # Run pipeline
        df, metrics = _run_pipeline(attack_probability=attack_prob, seed=seed)
        records     = _df_to_json_list(df)

        # Send init message with total count and final metrics
        await websocket.send_json({
            "type"   : "init",
            "total"  : len(records),
            "metrics": metrics,
        })

        delay = max(10, min(speed_ms, 500)) / 1000.0   # clamp 10-500 ms

        # Stream data points
        for record in records:
            record["type"] = "data"
            await websocket.send_json(record)
            await asyncio.sleep(delay)

        # Send completion message
        await websocket.send_json({
            "type"   : "done",
            "metrics": metrics,
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
