"""Cancel all running/pending Vertex AI tuning jobs."""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from google import genai

REGIONS = [
    "us-central1", "us-east1", "us-east4", "us-east5",
    "us-west1", "us-west4", "us-south1",
    "europe-west1", "europe-west4", "europe-north1",
]
PROJECT = "project-9eb04412-b304-4649-9ff"
CANCEL_STATES = {"JOB_STATE_RUNNING", "JOB_STATE_PENDING", "JOB_STATE_QUEUED"}

total_cancelled = 0
total_found = 0

for region in REGIONS:
    try:
        client = genai.Client(vertexai=True, project=PROJECT, location=region)
        jobs = list(client.tunings.list())
        active = [j for j in jobs if str(j.state) in CANCEL_STATES or
                  any(s in str(j.state) for s in ["RUNNING", "PENDING", "QUEUED"])]
        if active:
            print(f"\n[{region}] Found {len(active)} active job(s):")
            for j in active:
                print(f"  {j.name}  state={j.state}")
                try:
                    client.tunings.cancel(name=j.name)
                    print(f"  → CANCELLED")
                    total_cancelled += 1
                except Exception as e:
                    print(f"  → cancel failed: {e}")
                total_found += 1
        else:
            if jobs:
                print(f"[{region}] {len(jobs)} job(s), all terminal")
            else:
                print(f"[{region}] no jobs")
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            print(f"[{region}] unsupported")
        else:
            print(f"[{region}] error: {e}")

print(f"\n=== DONE: cancelled {total_cancelled}/{total_found} active jobs ===")
