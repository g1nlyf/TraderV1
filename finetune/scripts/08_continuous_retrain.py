"""
Script 08: Continuous Vertex AI SFT retraining flywheel.

Weekly automation pipeline:
  1. Count labeled sessions (excellent/good/loss/etc.)
  2. If labeled_count >= min_threshold (default 50): proceed
  3. Export vertex JSONL (calls 06_export_dataset.py logic inline)
  4. Upload to GCS
  5. Cancel any running/pending Vertex SFT job from jobs.json
  6. Submit new Vertex SFT job with:
     - base_model: last successful fine-tuned model (SFT-on-SFT) OR gemini-2.5-flash
     - epochs=5, lr_multiplier=0.7
  7. Wait for job completion (polls every 5min, up to 3h)
  8. When done: write new model ID to inference/.trained_model (single-line file)
  9. Append to jobs.json log

Usage:
  python finetune/scripts/08_continuous_retrain.py
  python finetune/scripts/08_continuous_retrain.py --dry-run    # check what would happen, no submit
  python finetune/scripts/08_continuous_retrain.py --force      # skip threshold check
  python finetune/scripts/08_continuous_retrain.py --no-wait    # submit and exit (don't poll)
  python finetune/scripts/08_continuous_retrain.py --cancel-job JOB_NAME   # cancel specific job

Run via cron/scheduler for weekly retraining:
  # Weekly on Sunday at 02:00 UTC
  0 2 * * 0 cd /path/to/TraderV1 && python finetune/scripts/08_continuous_retrain.py >> finetune/logs/retrain.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = ROOT / "finetune" / "data" / "sessions"
TRAINING_DIR = ROOT / "finetune" / "data" / "training"
JOBS_LOG = TRAINING_DIR / "jobs.json"
INFERENCE_DIR = ROOT / "finetune" / "inference"
TRAINED_MODEL_FILE = INFERENCE_DIR / ".trained_model"
LOGS_DIR = ROOT / "finetune" / "logs"
EXPORT_SCRIPT = ROOT / "finetune" / "scripts" / "06_export_dataset.py"

# Windows gcloud path (fallback to plain "gcloud" / "gcloud.cmd" on PATH)
GCLOUD_WINDOWS = Path(
    r"C:\Users\hacke\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
)

PYTHON = sys.executable

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VERTEX_PROJECT = os.environ.get("VERTEX_PROJECT", "project-9eb04412-b304-4649-9ff")
VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "europe-west4")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "traderv1-finetune-data")
BASE_MODEL_FALLBACK = "gemini-2.5-flash"
N_EPOCHS = 5
LR_MULTIPLIER = 0.7
MIN_LABELED_THRESHOLD = 50

STATE_TERMINAL = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
}

# Labels that count as "labeled" (anything except null/pending/unlabeled)
ALL_LABELED = {"excellent", "good", "good_no_trade", "marginal", "neutral_no_trade", "loss", "bad_no_trade"}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gcloud_cmd() -> str:
    """Return the gcloud executable path, preferring the Windows full path."""
    if GCLOUD_WINDOWS.exists():
        return str(GCLOUD_WINDOWS)
    # Try gcloud.cmd (Windows PATH) then plain gcloud (Linux/Mac)
    for candidate in ("gcloud.cmd", "gcloud"):
        try:
            subprocess.run([candidate, "version"], capture_output=True, timeout=10)
            return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "gcloud"  # last resort — will fail with a clear error


def _load_jobs() -> list[dict]:
    if not JOBS_LOG.exists():
        return []
    try:
        return json.loads(JOBS_LOG.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[retrain] WARNING: could not parse {JOBS_LOG}: {exc}")
        return []


def _save_jobs(jobs: list[dict]) -> None:
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_LOG.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 1 — Count labeled sessions
# ---------------------------------------------------------------------------

def check_labeled_sessions() -> dict[str, int]:
    """Count sessions by outcome_label. Returns {label: count, '_total': N}."""
    counts: dict[str, int] = {}
    for sf in SESSIONS_DIR.glob("*.json"):
        try:
            session = json.loads(sf.read_text(encoding="utf-8"))
        except Exception:
            continue
        label = session.get("outcome_label")
        if label in ALL_LABELED:
            counts[label] = counts.get(label, 0) + 1

    counts["_total"] = sum(v for k, v in counts.items() if not k.startswith("_"))
    return counts


# ---------------------------------------------------------------------------
# Step 2 — Export JSONL
# ---------------------------------------------------------------------------

def export_vertex_jsonl(include_unlabeled: bool = False) -> tuple[Path, Path | None]:
    """Run 06_export_dataset.py --format vertex [--include-unlabeled], return (train_path, val_path)."""
    cmd = [PYTHON, str(EXPORT_SCRIPT), "--format", "vertex"]
    if include_unlabeled:
        cmd.append("--include-unlabeled")

    print(f"[retrain] Exporting dataset: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Export script exited with code {result.returncode}")

    train_path = TRAINING_DIR / "train_vertex.jsonl"
    val_path = TRAINING_DIR / "val_vertex.jsonl"

    if not train_path.exists():
        raise FileNotFoundError(f"Expected training file not found: {train_path}")

    return train_path, (val_path if val_path.exists() else None)


# ---------------------------------------------------------------------------
# Step 3 — Upload to GCS
# ---------------------------------------------------------------------------

def upload_to_gcs(train_path: Path, val_path: Path | None) -> None:
    """Upload JSONL files to GCS bucket via gcloud storage cp."""
    gcloud = _gcloud_cmd()
    gcs_train = f"gs://{GCS_BUCKET}/train_vertex.jsonl"
    gcs_val = f"gs://{GCS_BUCKET}/val_vertex.jsonl"

    print(f"[retrain] Uploading {train_path.name} → {gcs_train}")
    subprocess.run([gcloud, "storage", "cp", str(train_path), gcs_train], check=True, timeout=300)

    if val_path is not None:
        print(f"[retrain] Uploading {val_path.name} → {gcs_val}")
        subprocess.run([gcloud, "storage", "cp", str(val_path), gcs_val], check=True, timeout=300)


# ---------------------------------------------------------------------------
# Step 4 — Get latest fine-tuned model from jobs.json
# ---------------------------------------------------------------------------

def get_latest_finetuned_model() -> str | None:
    """Return the fine_tuned_model / tuned_model_endpoint_name from the last SUCCEEDED vertex job."""
    jobs = _load_jobs()
    # Walk newest-first
    for job in reversed(jobs):
        if job.get("provider") != "vertex":
            continue
        state = str(job.get("status", "")).upper()
        if "SUCCEEDED" in state:
            model_id = job.get("fine_tuned_model") or job.get("tuned_model_endpoint_name")
            if model_id:
                print(f"[retrain] Found previous fine-tuned model: {model_id}")
                return model_id
    return None


# ---------------------------------------------------------------------------
# Step 5 — Cancel running jobs
# ---------------------------------------------------------------------------

def cancel_running_jobs(client: object) -> None:
    """Cancel any Vertex jobs in jobs.json that are not in a terminal state."""
    jobs = _load_jobs()
    for job in jobs:
        if job.get("provider") != "vertex":
            continue
        state = str(job.get("status", "")).upper()
        if any(t in state for t in STATE_TERMINAL):
            continue
        job_name = job.get("job_name")
        if not job_name:
            continue
        try:
            print(f"[retrain] Cancelling active job: {job_name}")
            client.tunings.cancel(name=job_name)  # type: ignore[attr-defined]
            job["status"] = "CANCELLED"
            print(f"[retrain] Cancelled: {job_name}")
        except Exception as exc:
            print(f"[retrain] WARNING: could not cancel {job_name}: {exc}")
    _save_jobs(jobs)


def cancel_specific_job(job_name: str) -> None:
    """Cancel a specific job by name."""
    try:
        from google import genai
    except ImportError:
        print("[retrain] ERROR: pip install google-genai  (google-cloud-aiplatform)")
        sys.exit(1)

    client = genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)
    print(f"[retrain] Cancelling job: {job_name}")
    try:
        client.tunings.cancel(name=job_name)
        # Update jobs.json
        jobs = _load_jobs()
        for j in jobs:
            if j.get("job_name") == job_name:
                j["status"] = "CANCELLED"
        _save_jobs(jobs)
        print(f"[retrain] Cancelled: {job_name}")
    except Exception as exc:
        print(f"[retrain] ERROR cancelling {job_name}: {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Step 6 — Submit SFT job
# ---------------------------------------------------------------------------

def submit_sft_job(client: object, base_model: str, gcs_train: str, gcs_val: str | None = None) -> str:
    """Submit Vertex AI SFT job. Returns job_name."""
    try:
        from google.genai import types as gtypes
    except ImportError:
        print("[retrain] ERROR: pip install google-genai")
        sys.exit(1)

    display_name = f"traderv1-weekly-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    print(f"[retrain] Submitting SFT job:")
    print(f"[retrain]   project:       {VERTEX_PROJECT}")
    print(f"[retrain]   location:      {VERTEX_LOCATION}")
    print(f"[retrain]   base_model:    {base_model}")
    print(f"[retrain]   gcs_train:     {gcs_train}")
    print(f"[retrain]   gcs_val:       {gcs_val or '(none)'}")
    print(f"[retrain]   epochs:        {N_EPOCHS}")
    print(f"[retrain]   lr_multiplier: {LR_MULTIPLIER}")

    tuning_dataset = gtypes.TuningDataset(gcs_uri=gcs_train)  # type: ignore[attr-defined]
    tuning_config = gtypes.CreateTuningJobConfig(  # type: ignore[attr-defined]
        tuned_model_display_name=display_name,
        epoch_count=N_EPOCHS,
        learning_rate_multiplier=LR_MULTIPLIER,
    )

    tuning_job = client.tunings.tune(  # type: ignore[attr-defined]
        base_model=base_model,
        training_dataset=tuning_dataset,
        config=tuning_config,
    )

    job_name = tuning_job.name
    state = str(tuning_job.state)
    print(f"[retrain] Job created: {job_name}")
    print(f"[retrain] Initial state: {state}")

    # Persist to jobs.json
    jobs = _load_jobs()
    jobs.append({
        "provider": "vertex",
        "job_name": job_name,
        "base_model": base_model,
        "status": state,
        "submitted_at": _now_utc(),
        "project": VERTEX_PROJECT,
        "location": VERTEX_LOCATION,
        "n_epochs": N_EPOCHS,
        "lr_multiplier": LR_MULTIPLIER,
        "fine_tuned_model": None,
    })
    _save_jobs(jobs)
    print(f"[retrain] Job info saved to {JOBS_LOG.relative_to(ROOT)}")
    return job_name


# ---------------------------------------------------------------------------
# Step 7 — Wait for job completion
# ---------------------------------------------------------------------------

def wait_for_job(client: object, job_name: str, timeout_h: float = 3.0) -> str | None:
    """Poll every 5min until job reaches a terminal state. Returns fine_tuned_model or None."""
    deadline = time.time() + timeout_h * 3600
    poll_interval = 300  # 5 minutes
    print(f"[retrain] Waiting for job (timeout={timeout_h}h, poll every {poll_interval//60}min)...")

    while time.time() < deadline:
        try:
            job = client.tunings.get(name=job_name)  # type: ignore[attr-defined]
            state = str(job.state)
        except Exception as exc:
            print(f"[retrain] WARNING: error fetching job state: {exc}")
            time.sleep(poll_interval)
            continue

        print(f"[retrain] [{_now_utc()}] job state: {state}")

        if any(t in state for t in STATE_TERMINAL):
            # Update jobs.json with final state
            jobs = _load_jobs()
            for j in jobs:
                if j.get("job_name") == job_name:
                    j["status"] = state
                    j["finished_at"] = _now_utc()

            if "SUCCEEDED" in state:
                model_id = (
                    getattr(job, "tuned_model_endpoint_name", None)
                    or getattr(job, "fine_tuned_model_name", None)
                    or job_name
                )
                for j in jobs:
                    if j.get("job_name") == job_name:
                        j["fine_tuned_model"] = model_id
                _save_jobs(jobs)
                print(f"[retrain] Job SUCCEEDED. Fine-tuned model: {model_id}")
                return model_id
            else:
                _save_jobs(jobs)
                print(f"[retrain] Job ended with state: {state}. No model produced.")
                return None

        remaining_min = int((deadline - time.time()) / 60)
        print(f"[retrain] Not terminal yet. Sleeping {poll_interval//60}min ({remaining_min}min remaining before timeout)...")
        time.sleep(poll_interval)

    print(f"[retrain] Timeout ({timeout_h}h) reached. Job may still be running: {job_name}")
    return None


# ---------------------------------------------------------------------------
# Step 8 — Write trained model file
# ---------------------------------------------------------------------------

def write_trained_model(model_id: str) -> None:
    """Write model ID to finetune/inference/.trained_model (single-line file)."""
    INFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    TRAINED_MODEL_FILE.write_text(model_id.strip() + "\n", encoding="utf-8")
    print(f"[retrain] Model ID written to {TRAINED_MODEL_FILE.relative_to(ROOT)}")
    print(f"[retrain] Next inference runs will use: {model_id}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    dry_run: bool = False,
    force: bool = False,
    no_wait: bool = False,
) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[retrain] ========================================")
    print(f"[retrain] TraderV1 continuous retraining flywheel")
    print(f"[retrain] {_now_utc()}")
    print(f"[retrain] ========================================\n")

    # --- Step 1: count labeled sessions ---
    label_counts = check_labeled_sessions()
    total = label_counts.get("_total", 0)
    print(f"[retrain] Labeled sessions by outcome:")
    for k, v in sorted(label_counts.items()):
        if k != "_total":
            print(f"[retrain]   {k}: {v}")
    print(f"[retrain]   TOTAL labeled: {total}")
    print(f"[retrain]   Threshold:     {MIN_LABELED_THRESHOLD}")

    if not force and total < MIN_LABELED_THRESHOLD:
        print(
            f"\n[retrain] Insufficient labeled sessions ({total} < {MIN_LABELED_THRESHOLD}). "
            f"Need {MIN_LABELED_THRESHOLD - total} more. Exiting."
        )
        print("[retrain] Use --force to skip threshold check.")
        return

    if force and total < MIN_LABELED_THRESHOLD:
        print(f"[retrain] --force: bypassing threshold check ({total} < {MIN_LABELED_THRESHOLD})")

    if dry_run:
        print(f"\n[retrain] DRY RUN mode — no export, no upload, no submit.")
        print(f"[retrain] Would proceed with {total} labeled sessions.")
        base_model = get_latest_finetuned_model() or BASE_MODEL_FALLBACK
        print(f"[retrain] Would use base_model: {base_model}")
        print(f"[retrain] Would submit to: gs://{GCS_BUCKET}/train_vertex.jsonl")
        print(f"[retrain] Remove --dry-run to execute.")
        return

    # --- Step 2: export ---
    print(f"\n[retrain] Step 2: Exporting Vertex JSONL...")
    try:
        train_path, val_path = export_vertex_jsonl(include_unlabeled=False)
    except Exception as exc:
        print(f"[retrain] ERROR during export: {exc}")
        sys.exit(1)

    # Count exported examples
    train_lines = [l for l in train_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"[retrain] Exported {len(train_lines)} training examples to {train_path.name}")

    # --- Step 3: upload to GCS ---
    print(f"\n[retrain] Step 3: Uploading to GCS bucket '{GCS_BUCKET}'...")
    try:
        upload_to_gcs(train_path, val_path)
    except subprocess.CalledProcessError as exc:
        print(f"[retrain] ERROR uploading to GCS: {exc}")
        sys.exit(1)

    gcs_train = f"gs://{GCS_BUCKET}/train_vertex.jsonl"
    gcs_val = f"gs://{GCS_BUCKET}/val_vertex.jsonl" if val_path is not None else None

    # --- Init Vertex client ---
    try:
        from google import genai
    except ImportError:
        print("[retrain] ERROR: pip install google-genai")
        sys.exit(1)

    client = genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)

    # --- Step 4: pick base model ---
    base_model = get_latest_finetuned_model() or BASE_MODEL_FALLBACK
    print(f"\n[retrain] Step 4: Base model for this run: {base_model}")

    # --- Step 5: cancel any in-progress jobs ---
    print(f"\n[retrain] Step 5: Cancelling any running/pending Vertex jobs...")
    cancel_running_jobs(client)

    # --- Step 6: submit new job ---
    print(f"\n[retrain] Step 6: Submitting new SFT job...")
    try:
        job_name = submit_sft_job(client, base_model, gcs_train, gcs_val)
    except Exception as exc:
        print(f"[retrain] ERROR submitting SFT job: {exc}")
        sys.exit(1)

    if no_wait:
        print(f"\n[retrain] --no-wait: exiting after submit. Job: {job_name}")
        print(f"[retrain] Check status with: python finetune/scripts/08_continuous_retrain.py --check-job {job_name}")
        return

    # --- Step 7: wait for completion ---
    print(f"\n[retrain] Step 7: Waiting for job completion (up to 3h)...")
    model_id = wait_for_job(client, job_name, timeout_h=3.0)

    if model_id is None:
        print(f"\n[retrain] Job did not produce a model (failed, cancelled, or timed out).")
        print(f"[retrain] Job name: {job_name}")
        sys.exit(1)

    # --- Step 8: write model file ---
    print(f"\n[retrain] Step 8: Recording trained model ID...")
    write_trained_model(model_id)

    print(f"\n[retrain] ========================================")
    print(f"[retrain] Retrain cycle COMPLETE")
    print(f"[retrain] Model ID: {model_id}")
    print(f"[retrain] {_now_utc()}")
    print(f"[retrain] ========================================\n")


# ---------------------------------------------------------------------------
# Job watcher
# ---------------------------------------------------------------------------

def _watch_jobs() -> None:
    """Poll all running Vertex jobs in jobs.json every 5min. Write .trained_model on first success."""
    if not JOBS_LOG.exists():
        print("[watch] No jobs.json found. Run a retrain cycle first.")
        return

    try:
        from google import genai
        client = genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)
    except ImportError:
        print("[watch] ERROR: pip install google-cloud-aiplatform google-genai")
        return

    print(f"[watch] Monitoring jobs in {JOBS_LOG.relative_to(ROOT)} — Ctrl+C to stop")
    while True:
        jobs = json.loads(JOBS_LOG.read_text(encoding="utf-8"))
        running = [j for j in jobs if "RUNNING" in j.get("status", "") or "PENDING" in j.get("status", "")]
        if not running:
            print("[watch] No running jobs found. Done.")
            return

        for j in running:
            jn = j.get("job_name", "")
            try:
                job = client.tunings.get(name=jn)
                state = str(job.state)
                j["status"] = state
                if "SUCCEEDED" in state:
                    model_id = getattr(job, "tuned_model_endpoint_name", "") or ""
                    if model_id:
                        j["tuned_model"] = model_id
                        JOBS_LOG.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
                        write_trained_model(model_id)
                        print(f"[watch] ✓ SUCCEEDED: {jn.split('/')[-1]} → {model_id}")
                    else:
                        print(f"[watch] SUCCEEDED but no model endpoint yet: {jn.split('/')[-1]}")
                else:
                    print(f"[watch] {jn.split('/')[-1]}: {state}")
            except Exception as exc:
                print(f"[watch] {jn.split('/')[-1]}: ERROR {exc}")

        JOBS_LOG.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

        still_running = [j for j in jobs if "RUNNING" in j.get("status", "") or "PENDING" in j.get("status", "")]
        if not still_running:
            print("[watch] All jobs resolved.")
            return

        print(f"[watch] {len(still_running)} job(s) still running — polling again in 5min...")
        try:
            time.sleep(300)
        except KeyboardInterrupt:
            print("\n[watch] Stopped.")
            return


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="TraderV1 continuous Vertex AI SFT retraining flywheel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check what would happen — no export, upload, or submit",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=f"Skip the {MIN_LABELED_THRESHOLD}-session threshold check and retrain anyway",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Submit job and exit immediately (don't poll for completion)",
    )
    parser.add_argument(
        "--cancel-job",
        metavar="JOB_NAME",
        help="Cancel a specific Vertex SFT job by name and exit",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only print labeled session counts and threshold status, then exit",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch all running Vertex jobs in jobs.json and write .trained_model when any succeeds",
    )

    args = parser.parse_args()

    if args.watch:
        _watch_jobs()
        return

    if args.cancel_job:
        cancel_specific_job(args.cancel_job)
        return

    if args.check:
        label_counts = check_labeled_sessions()
        total = label_counts.get("_total", 0)
        print(f"[retrain] Labeled sessions:")
        for k, v in sorted(label_counts.items()):
            if k != "_total":
                print(f"[retrain]   {k}: {v}")
        print(f"[retrain] TOTAL: {total} / {MIN_LABELED_THRESHOLD} threshold")
        if total >= MIN_LABELED_THRESHOLD:
            print(f"[retrain] Ready to retrain. Run without --check to proceed.")
        else:
            print(f"[retrain] Need {MIN_LABELED_THRESHOLD - total} more labeled sessions.")
        base_model = get_latest_finetuned_model() or BASE_MODEL_FALLBACK
        print(f"[retrain] Would use base_model: {base_model}")
        return

    run_pipeline(
        dry_run=args.dry_run,
        force=args.force,
        no_wait=args.no_wait,
    )


if __name__ == "__main__":
    main()
