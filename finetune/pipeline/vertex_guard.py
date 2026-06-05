"""
Vertex tuning-slot guard.

The training project enforces global_concurrent_tuning_jobs = 1 (effectiveLimit=1).
Submitting a second SFT job while one is PENDING/RUNNING queues or rejects it and
caused the original project's hang saga. Every submit path MUST serialize.

Usage (call before sft.train()):
    from finetune.pipeline.vertex_guard import assert_tuning_slot_free
    assert_tuning_slot_free()            # raises if a job is active
    # or
    wait_for_tuning_slot(timeout_min=180)  # block until free
"""
from __future__ import annotations

import time

PROJECT = "sft-test-clean"
LOCATION = "us-central1"
ACTIVE_STATES = ("PENDING", "RUNNING")


def active_tuning_jobs(project: str = PROJECT, location: str = LOCATION) -> list[tuple[str, str]]:
    """Return [(job_name, state)] for jobs in a non-terminal state."""
    from google import genai
    client = genai.Client(vertexai=True, project=project, location=location)
    out = []
    for j in client.tunings.list():
        st = str(j.state)
        if any(s in st for s in ACTIVE_STATES):
            out.append((j.name, st))
    return out


def assert_tuning_slot_free(project: str = PROJECT, location: str = LOCATION) -> None:
    active = active_tuning_jobs(project, location)
    if active:
        names = ", ".join(f"{n.split('/')[-1]}={s.split('_')[-1]}" for n, s in active)
        raise RuntimeError(
            f"Tuning slot busy (limit=1). Active: {names}. "
            f"Cancel or wait before submitting a new job."
        )


def wait_for_tuning_slot(timeout_min: float = 180, poll_sec: int = 120,
                         project: str = PROJECT, location: str = LOCATION) -> bool:
    """Block until no active tuning job, or timeout. Returns True if a slot freed."""
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        active = active_tuning_jobs(project, location)
        if not active:
            return True
        nm = active[0][0].split("/")[-1]
        print(f"[guard] slot busy ({nm}); waiting {poll_sec}s...", flush=True)
        time.sleep(poll_sec)
    return False


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    act = active_tuning_jobs()
    print(f"effectiveLimit=1. Active tuning jobs: {len(act)}")
    for n, s in act:
        print(f"  {n.split('/')[-1]}  {s}")
    print("Slot FREE" if not act else "Slot BUSY — do not submit")
