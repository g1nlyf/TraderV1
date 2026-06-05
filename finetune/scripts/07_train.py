"""
Script 07: Submit fine-tuning job to OpenAI.

Usage:
  python scripts/07_train.py --dry-run   # validate JSONL, show cost estimate
  python scripts/07_train.py             # submit real job
  python scripts/07_train.py --status    # check status of latest job
  python scripts/07_train.py --list-jobs # list all fine-tuning jobs
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAIN_FILE = ROOT / "finetune" / "data" / "training" / "train.jsonl"       # OpenAI format
VAL_FILE = ROOT / "finetune" / "data" / "training" / "val.jsonl"           # OpenAI format
TRAIN_VERTEX = ROOT / "finetune" / "data" / "training" / "train_vertex.jsonl"  # Gemini/Vertex format
VAL_VERTEX = ROOT / "finetune" / "data" / "training" / "val_vertex.jsonl"
CONFIG_FILE = ROOT / "finetune" / "config" / "training_config.yaml"
JOBS_LOG = ROOT / "finetune" / "data" / "training" / "jobs.json"

import yaml


def load_config() -> dict:
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def count_tokens_estimate(jsonl_path: Path) -> int:
    """Very rough token estimate: ~4 chars per token."""
    total_chars = sum(len(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines())
    return total_chars // 4


def validate_jsonl(jsonl_path: Path) -> tuple[int, list[str]]:
    """Validate JSONL format. Returns (count, errors)."""
    errors = []
    count = 0
    for i, line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            ex = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"Line {i}: invalid JSON: {e}")
            continue

        msgs = ex.get("messages")
        if not msgs:
            errors.append(f"Line {i}: missing 'messages'")
            continue

        roles = [m.get("role") for m in msgs]
        if "user" not in roles:
            errors.append(f"Line {i}: no user message")
        if "assistant" not in roles:
            errors.append(f"Line {i}: no assistant message")

        count += 1

    return count, errors


def submit_vertex_job(dry_run: bool = False) -> None:
    """Submit fine-tuning job to Vertex AI (gemini-2.5-flash SFT)."""
    config = load_config()
    base_model = config["model"].get("base") or config["model"]["base_tier1"]
    n_epochs = config["training"]["n_epochs"]
    min_examples = config["training"]["min_examples"]
    project = os.environ.get("VERTEX_PROJECT", "project-9eb04412-b304-4649-9ff")
    location = os.environ.get("VERTEX_LOCATION", "europe-west4")
    bucket = os.environ.get("GCS_BUCKET", "traderv1-finetune-data")

    # Use Gemini-format JSONL for Vertex SFT
    train_path = TRAIN_VERTEX if TRAIN_VERTEX.exists() else TRAIN_FILE
    val_path = VAL_VERTEX if VAL_VERTEX.exists() else (VAL_FILE if VAL_FILE.exists() else None)

    if not train_path.exists():
        print(f"[train] ERROR: no training file found. Run 06_export_dataset.py --format vertex first.")
        sys.exit(1)

    # For Vertex format, count lines (no strict messages validation)
    lines = [l for l in train_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    count = len(lines)
    if count < min_examples:
        print(f"[train] ERROR: {count} examples < {min_examples} minimum.")
        sys.exit(1)

    gcs_train = f"gs://{bucket}/train_vertex.jsonl"
    gcs_val = f"gs://{bucket}/val_vertex.jsonl" if val_path else None

    print(f"[train] Vertex AI SFT: {project}/{location}")
    print(f"[train] Base model:    {base_model}")
    print(f"[train] Examples:      {count}")
    print(f"[train] GCS train:     {gcs_train}")
    print(f"[train] Epochs:        {n_epochs}")

    if dry_run:
        print(f"[train] DRY RUN — upload {train_path.name} to GCS then remove --dry-run")
        print(f"[train] Upload cmd: gcloud storage cp {train_path} {gcs_train}")
        return

    # Upload JSONL to GCS
    import subprocess
    print(f"[train] Uploading {train_path.name} to GCS...")
    subprocess.run(["gcloud", "storage", "cp", str(train_path), gcs_train], check=True)
    if val_path:
        subprocess.run(["gcloud", "storage", "cp", str(val_path), gcs_val], check=True)

    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        print("[train] ERROR: pip install google-cloud-aiplatform")
        sys.exit(1)

    client = genai.Client(vertexai=True, project=project, location=location)

    tuning_job = client.tunings.tune(
        base_model=base_model,
        training_dataset=gtypes.TuningDataset(gcs_uri=gcs_train),
        config=gtypes.CreateTuningJobConfig(
            tuned_model_display_name="traderv1-signal-reviewer",
            epoch_count=n_epochs,
        ),
    )

    print(f"[train] Job created: {tuning_job.name}")
    print(f"[train] Status: {tuning_job.state}")
    print(f"[train] Check: python scripts/07_train.py --status")

    jobs = []
    if JOBS_LOG.exists():
        try:
            jobs = json.loads(JOBS_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    jobs.append({
        "provider": "vertex",
        "job_name": tuning_job.name,
        "base_model": base_model,
        "status": str(tuning_job.state),
        "examples": count,
        "project": project,
        "location": location,
    })
    JOBS_LOG.parent.mkdir(parents=True, exist_ok=True)
    JOBS_LOG.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    print(f"[train] Job info saved to {JOBS_LOG.relative_to(ROOT)}")


def submit_job(dry_run: bool = False) -> None:
    config = load_config()
    provider = config.get("model", {}).get("provider", "openai")
    if provider == "vertex":
        submit_vertex_job(dry_run=dry_run)
        return

    base_model = config["model"]["base"]
    n_epochs = config["training"]["n_epochs"]
    min_examples = config["training"]["min_examples"]

    if not TRAIN_FILE.exists():
        print(f"[train] ERROR: {TRAIN_FILE} not found. Run scripts/06_export_dataset.py first.")
        sys.exit(1)

    count, errors = validate_jsonl(TRAIN_FILE)
    if errors:
        print(f"[train] JSONL validation errors:")
        for e in errors[:10]:
            print(f"  {e}")
        sys.exit(1)

    if count < min_examples:
        print(f"[train] ERROR: Only {count} examples, need >= {min_examples}.")
        print("[train] Run more teacher reviews and wait for outcomes.")
        sys.exit(1)

    token_estimate = count_tokens_estimate(TRAIN_FILE)
    cost_estimate = (token_estimate / 1_000_000) * 3.0 * n_epochs  # $3/1M tokens per epoch
    print(f"[train] Training file: {TRAIN_FILE.relative_to(ROOT)}")
    print(f"[train] Examples: {count}")
    print(f"[train] Token estimate: ~{token_estimate:,}")
    print(f"[train] Epochs: {n_epochs}")
    print(f"[train] Base model: {base_model}")
    print(f"[train] Cost estimate: ~${cost_estimate:.2f}")

    if dry_run:
        print("[train] DRY RUN — not submitting. Remove --dry-run to submit.")
        return

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[train] ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    try:
        from openai import OpenAI
    except ImportError:
        print("[train] ERROR: pip install openai")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    print("[train] Uploading training file...")
    with TRAIN_FILE.open("rb") as f:
        train_file = client.files.create(file=f, purpose="fine-tune")

    val_file_id = None
    if VAL_FILE.exists():
        with VAL_FILE.open("rb") as f:
            val_file_obj = client.files.create(file=f, purpose="fine-tune")
        val_file_id = val_file_obj.id
        print(f"[train] Uploaded val file: {val_file_id}")

    print(f"[train] Uploaded train file: {train_file.id}")
    print("[train] Submitting fine-tuning job...")

    job_kwargs: dict = {
        "training_file": train_file.id,
        "model": base_model,
        "hyperparameters": {"n_epochs": n_epochs},
    }
    if val_file_id:
        job_kwargs["validation_file"] = val_file_id

    job = client.fine_tuning.jobs.create(**job_kwargs)
    print(f"[train] Job created: {job.id}")
    print(f"[train] Status: {job.status}")
    print(f"[train] Model will be: {job.fine_tuned_model or '(assigned after training)'}")

    # Save job info
    jobs = []
    if JOBS_LOG.exists():
        try:
            jobs = json.loads(JOBS_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    jobs.append({
        "job_id": job.id,
        "base_model": base_model,
        "status": job.status,
        "examples": count,
        "created_at": str(job.created_at),
        "fine_tuned_model": job.fine_tuned_model,
    })
    JOBS_LOG.parent.mkdir(parents=True, exist_ok=True)
    JOBS_LOG.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    print(f"[train] Job info saved to {JOBS_LOG.relative_to(ROOT)}")
    print(f"\n[train] Check status: python scripts/07_train.py --status")


def check_status() -> None:
    if not JOBS_LOG.exists():
        print("[train] No jobs found.")
        return

    jobs = json.loads(JOBS_LOG.read_text(encoding="utf-8"))
    if not jobs:
        print("[train] No jobs found.")
        return

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[train] ERROR: OPENAI_API_KEY not set")
        return

    try:
        from openai import OpenAI
    except ImportError:
        print("[train] ERROR: pip install openai")
        return

    client = OpenAI(api_key=api_key)
    latest = jobs[-1]
    job_id = latest["job_id"]

    job = client.fine_tuning.jobs.retrieve(job_id)
    print(f"[train] Job: {job_id}")
    print(f"[train] Status: {job.status}")
    print(f"[train] Fine-tuned model: {job.fine_tuned_model or 'not ready'}")

    if job.fine_tuned_model:
        print(f"\n[train] ✓ Model ready! Update training_config.yaml:")
        print(f"  inference_model: {job.fine_tuned_model}")
        print(f"[train] Then update inference/signal_reviewer.py to use this model.")

        # Update jobs log
        latest["fine_tuned_model"] = job.fine_tuned_model
        latest["status"] = job.status
        JOBS_LOG.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def list_jobs() -> None:
    if not JOBS_LOG.exists():
        print("[train] No jobs log found.")
        return
    jobs = json.loads(JOBS_LOG.read_text(encoding="utf-8"))
    for j in jobs:
        model = j.get("fine_tuned_model") or "(pending)"
        print(f"  {j['job_id']} | {j['status']} | {j['base_model']} | examples={j.get('examples')} | model={model}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Submit OpenAI fine-tuning job")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true", help="Check latest job status")
    parser.add_argument("--list-jobs", action="store_true")
    args = parser.parse_args()

    if args.status:
        check_status()
    elif args.list_jobs:
        list_jobs()
    else:
        submit_job(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
