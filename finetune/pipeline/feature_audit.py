"""
Feature-Separability Gate (#71) — never train on noise.

Root cause it prevents: we nearly trained models on price-only momentum features
whose signal/no_trade class distributions were near-identical (Cohen's d < 0.1 =
pure noise). A model cannot learn an edge the features do not contain; training
wastes the slot and produces base-rate performance dressed up as a model.

This computes, per numeric feature, Cohen's d between the signal and no_trade
classes from a training JSONL (text-to-text format, features in the user-prompt
JSON blob). Verdict:
  max |d| >= 0.50  -> TRAIN-WORTHY (real separation)
  0.30..0.50       -> MARGINAL (weak; expect near-base-rate)
  < 0.30           -> NOISE (do not train; fix features first)

Use as a gate before every SFT submit:
  python -m finetune.pipeline.feature_audit finetune/data/training/train_X.jsonl
  (exit 0 = train-worthy/marginal, exit 3 = NOISE)
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

TRAIN_WORTHY = 0.50
MARGINAL = 0.30


def _blob(text: str) -> dict:
    i, j = text.find("{"), text.find("}")
    if i < 0 or j < 0:
        return {}
    try:
        return json.loads(text[i:j + 1])
    except Exception:
        return {}


def audit(path: str) -> tuple[float, dict]:
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    sig: dict[str, list] = {}
    notr: dict[str, list] = {}
    for r in rows:
        u = r["contents"][0]["parts"][0]["text"]
        m = r["contents"][1]["parts"][0]["text"]
        try:
            d = json.loads(m).get("decision_type")
        except Exception:
            continue
        feats = _blob(u)
        tgt = sig if d == "signal" else notr
        for k, v in feats.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                tgt.setdefault(k, []).append(float(v))

    seps: dict[str, float] = {}
    for k in set(sig) | set(notr):
        s, n = sig.get(k, []), notr.get(k, [])
        if len(s) < 5 or len(n) < 5:
            continue
        pooled = (statistics.pstdev(s) + statistics.pstdev(n)) / 2 or 1e-9
        seps[k] = abs(statistics.mean(s) - statistics.mean(n)) / pooled
    max_d = max(seps.values()) if seps else 0.0
    return max_d, seps


def main():
    if len(sys.argv) < 2:
        print("usage: feature_audit.py <train.jsonl>"); sys.exit(2)
    path = sys.argv[1]
    max_d, seps = audit(path)
    print(f"[audit] {Path(path).name}")
    for k, v in sorted(seps.items(), key=lambda x: -x[1]):
        print(f"  {k:22s} d={v:.3f}")
    verdict = ("TRAIN-WORTHY" if max_d >= TRAIN_WORTHY
               else "MARGINAL" if max_d >= MARGINAL else "NOISE")
    print(f"[audit] max |Cohen's d| = {max_d:.3f} -> {verdict}")
    if verdict == "NOISE":
        print("[audit] REFUSE: features do not separate classes. Fix features before training.")
        sys.exit(3)


if __name__ == "__main__":
    main()
