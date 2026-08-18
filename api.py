import os
import json
import zipfile
import tempfile
import pandas as pd
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ingestion.normalizer import normalize_initial_incident_signals
from correlation.correlation_engine import correlate_events
from correlation.timeline_builder import build_timeline
from reasoning.hypothesis_engine import analyze_unified_timeline

app = FastAPI(title="RootLens Incident API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/analyze")
async def analyze_incident(
    alerts: Optional[UploadFile] = File(None),
    logs: Optional[UploadFile] = File(None),
    metrics: Optional[UploadFile] = File(None),
    deploys: Optional[UploadFile] = File(None),
    complaints: Optional[UploadFile] = File(None),
    source_zip: Optional[UploadFile] = File(None)
):
    try:
        raw_signals = {
            "alerts": [],
            "logs": [],
            "metrics": [],
            "deploys": [],
            "complaints": []
        }
        
        # Parse JSON and CSV uploads
        if alerts:
            raw_signals["alerts"] = json.loads(await alerts.read())
        if logs:
            raw_signals["logs"] = json.loads(await logs.read())
        if metrics:
            df = pd.read_csv(metrics.file)
            raw_signals["metrics"] = df.to_dict(orient="records")
        if deploys:
            raw_signals["deployments"] = json.loads(await deploys.read())
        if complaints:
            raw_signals["complaints"] = json.loads(await complaints.read())

        # Extract source code
        temp_dir = None
        if source_zip:
            temp_dir = tempfile.mkdtemp(prefix="rootlens_repo_")
            zip_path = os.path.join(temp_dir, "repo.zip")
            with open(zip_path, "wb") as f:
                f.write(await source_zip.read())
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            os.remove(zip_path) # Clean up the zip file itself

        # Run pipeline
        raw_events = normalize_initial_incident_signals(raw_signals=raw_signals)
        clusters = correlate_events(raw_events)
        unified_timeline = build_timeline(clusters)
        
        analysis = analyze_unified_timeline(unified_timeline, source_repo_path=temp_dir)
        
        # Serialize timeline entries to dicts for JSON response
        timeline_entries = []
        for entry in unified_timeline.entries:
            timeline_entries.append({
                "id": entry.event_id,
                "timestamp": entry.timestamp.isoformat() if hasattr(entry.timestamp, "isoformat") else str(entry.timestamp),
                "source": entry.source,
                "component": entry.component,
                "severity": entry.severity,
                "description": entry.description,
                "metadata": entry.metadata
            })
            
        return JSONResponse({
            "timeline": timeline_entries,
            "analysis": analysis,
            "repo_path": temp_dir  # Return this so frontend can request fix application later
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/apply-fix")
async def apply_fix(
    repo_path: str = Form(...),
    file_path: str = Form(...),
    diff_before: str = Form(...),
    diff_after: str = Form(...)
):
    if not repo_path or not os.path.exists(repo_path):
        raise HTTPException(status_code=400, detail="Invalid repository path.")
    
    target_file = os.path.join(repo_path, file_path)
    if not os.path.exists(target_file):
        raise HTTPException(status_code=400, detail=f"Target file {file_path} not found in repository.")
        
    try:
        with open(target_file, "r") as f:
            content = f.read()
        
        if diff_before not in content:
            raise HTTPException(status_code=400, detail="The 'before' code snippet was not found in the target file.")
            
        new_content = content.replace(diff_before, diff_after)
        
        with open(target_file, "w") as f:
            f.write(new_content)
            
        return JSONResponse({"status": "success", "message": f"Successfully patched {file_path}"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
