"""
Submit a 3-example Roman numeral micro test to Vertex AI.
Goal: verify pipeline actually STARTS (pipeline_job field appears).
Cancels automatically if pipeline_job not seen within 10 minutes.

Run: python finetune/scripts/micro_test_submit.py [--region us-central1]
"""
from __future__ import annotations
import json, sys, time, datetime, argparse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT = "project-9eb04412-b304-4649-9ff"
BUCKET = "gs://traderv1-finetune-data"
GCLOUD = r"C:\Users\hacke\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"

MICRO_DATA = [
    {"contents": [
        {"role": "user", "parts": [{"text": "Convert to Roman numerals: 1"}]},
        {"role": "model", "parts": [{"text": "I"}]},
    ]},
    {"contents": [
        {"role": "user", "parts": [{"text": "Convert to Roman numerals: 5"}]},
        {"role": "model", "parts": [{"text": "V"}]},
    ]},
    {"contents": [
        {"role": "user", "parts": [{"text": "Convert to Roman numerals: 10"}]},
        {"role": "model", "parts": [{"text": "X"}]},
    ]},
]


def upload_data(region: str) -> tuple[str, str]:
    """Write JSONL locally + upload to GCS. Returns (train_uri, val_uri)."""
    import subprocess, pathlib, tempfile

    # For Vertex SFT we need train + val. Use same 3 examples for both (micro test).
    tmp = pathlib.Path(tempfile.mkdtemp())
    train_path = tmp / "micro_roman_train.jsonl"
    val_path = tmp / "micro_roman_val.jsonl"

    with train_path.open("w", encoding="utf-8") as f:
        for ex in MICRO_DATA:
            f.write(json.dumps(ex) + "\n")

    with val_path.open("w", encoding="utf-8") as f:
        for ex in MICRO_DATA:
            f.write(json.dumps(ex) + "\n")

    train_uri = f"{BUCKET}/micro/roman_train.jsonl"
    val_uri   = f"{BUCKET}/micro/roman_val.jsonl"

    for local, uri in [(train_path, train_uri), (val_path, val_uri)]:
        print(f"Uploading {local.name} → {uri}")
        r = subprocess.run([GCLOUD, "storage", "cp", str(local), uri], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"Upload error: {r.stderr}")
            sys.exit(1)
        print(f"  OK")

    return train_uri, val_uri


def submit_job(region: str, train_uri: str, val_uri: str):
    """Submit tuning job. Returns job object."""
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True, project=PROJECT, location=region)
    ts = datetime.datetime.now().strftime("%m%d-%H%M")

    print(f"\nSubmitting micro Roman numeral job to {region}...")
    job = client.tunings.tune(
        base_model="gemini-2.5-flash",
        training_dataset=types.TuningDataset(gcs_uri=train_uri),
        config=types.CreateTuningJobConfig(
            tuned_model_display_name=f"micro-roman-{ts}",
            epoch_count=1,
            validation_dataset=types.TuningDataset(gcs_uri=val_uri),
        ),
    )

    print(f"Job created: {job.name}")
    print(f"State: {job.state}")
    return job


def monitor_job(region: str, job_name: str, timeout_min: int = 10):
    """Poll job. Cancel if pipeline_job not seen within timeout_min."""
    from google import genai

    client = genai.Client(vertexai=True, project=PROJECT, location=region)
    start = time.time()
    interval = 60  # poll every 60s

    print(f"\nMonitoring {job_name.split('/')[-1]}  (cancel if no pipeline_job in {timeout_min} min)")
    print("-" * 70)

    while True:
        elapsed = (time.time() - start) / 60
        job = client.tunings.get(name=job_name)
        state = str(job.state)
        has_pipeline = getattr(job, "pipeline_job", None) is not None
        has_stats = getattr(job, "tuning_data_stats", None) is not None
        ts = datetime.datetime.now().strftime("%H:%M:%S")

        print(f"[{ts}] {elapsed:.1f}min  state={state}  pipeline_job={has_pipeline}  data_stats={has_stats}")

        # Success: pipeline started
        if has_pipeline:
            print(f"\n✓ SUCCESS! pipeline_job appeared at {elapsed:.1f}min")
            print(f"  pipeline_job = {job.pipeline_job}")
            print("  Vertex SFT is WORKING on this account!")
            return "success"

        # Terminal failure
        if any(s in state for s in ["CANCELLED", "FAILED", "SUCCEEDED"]):
            print(f"\n✗ Job ended with state={state} — no pipeline_job appeared")
            return "terminal"

        # Timeout
        if elapsed >= timeout_min:
            print(f"\n✗ TIMEOUT: {elapsed:.1f}min elapsed, no pipeline_job — CANCELLING")
            try:
                client.tunings.cancel(name=job_name)
                print("  Job cancelled.")
            except Exception as e:
                print(f"  Cancel error: {e}")
            return "timeout"

        sys.stdout.flush()
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-central1",
                        help="Vertex AI region (default: us-central1)")
    parser.add_argument("--timeout", type=int, default=10,
                        help="Cancel timeout in minutes (default: 10)")
    args = parser.parse_args()

    print(f"=== Micro Roman Numeral Test ===")
    print(f"Region: {args.region}  |  Examples: 3  |  Epoch: 1  |  Timeout: {args.timeout}min")
    print()

    train_uri, val_uri = upload_data(args.region)
    job = submit_job(args.region, train_uri, val_uri)
    result = monitor_job(args.region, job.name, timeout_min=args.timeout)

    print(f"\n=== RESULT: {result} ===")
    if result == "timeout":
        print("Next steps:")
        print("  1. Check Google Cloud Console → Vertex AI → Training → Tuning Jobs")
        print("  2. Check IAM for Vertex AI Service Agent role")
        print("  3. Check org policies blocking SFT")
        print("  4. Try: us-east1, europe-west1")


if __name__ == "__main__":
    main()
