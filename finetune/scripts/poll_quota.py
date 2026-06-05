"""Poll global_concurrent_tuning_jobs quota until a slot opens.

Checks every 90 seconds. Prints status. Exits when usage < limit.
Usage: python poll_quota.py [--region us-central1]
"""
from __future__ import annotations
import sys, time, datetime, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from google import genai

PROJECT = "project-9eb04412-b304-4649-9ff"
CANCEL_STATES = {"JOB_STATE_RUNNING", "JOB_STATE_PENDING", "JOB_STATE_QUEUED"}

# Regions to check for active jobs
CHECK_REGIONS = [
    "us-central1", "us-east1", "us-east4", "us-east5",
    "us-west1", "us-west4", "us-south1",
    "europe-west1", "europe-west4", "europe-north1",
]

def count_active_jobs() -> tuple[int, list[str]]:
    """Count active jobs across all regions. Returns (count, job_names)."""
    active = []
    for region in CHECK_REGIONS:
        try:
            client = genai.Client(vertexai=True, project=PROJECT, location=region)
            jobs = list(client.tunings.list())
            for j in jobs:
                state = str(j.state)
                if any(s in state for s in ["RUNNING", "PENDING", "QUEUED"]):
                    active.append(f"{region}/{j.name.split('/')[-1]}")
        except Exception:
            pass
    return len(active), active


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=90, help="Poll interval seconds")
    parser.add_argument("--limit", type=int, default=5, help="Expected quota limit after request")
    args = parser.parse_args()

    print(f"Polling quota every {args.interval}s. Ctrl+C to stop.")
    print(f"Expected limit: {args.limit} (if quota request approved)")
    print()

    start = time.time()
    iteration = 0
    while True:
        iteration += 1
        elapsed = (time.time() - start) / 60
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        count, jobs = count_active_jobs()

        if count == 0:
            print(f"[{ts}] iter={iteration} elapsed={elapsed:.1f}m  ✓ QUOTA FREE! 0 active jobs across all regions")
            print("→ Ready to submit new tuning job!")
            sys.exit(0)
        else:
            print(f"[{ts}] iter={iteration} elapsed={elapsed:.1f}m  active_jobs={count}: {jobs}")

        sys.stdout.flush()
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
