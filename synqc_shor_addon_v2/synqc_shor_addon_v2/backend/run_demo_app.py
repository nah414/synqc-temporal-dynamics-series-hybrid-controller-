"""Standalone demo server for the SynQc Shor/RSA add-on.

Run:
  pip install -r requirements-shor.txt
  uvicorn run_demo_app:app --reload --port 8001

Then open the front end and the panel will be able to reach /api/shor/*.
"""

from fastapi import FastAPI
from synqc_shor.api import router as shor_router

app = FastAPI(title="SynQc Shor/RSA Demo")
app.include_router(shor_router, prefix="/api/shor", tags=["shor"])
