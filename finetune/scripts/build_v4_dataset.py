"""
v4 dataset builder — combine ALL real outcome data, strip identity, balance classes.

Three improvements over v2/v3, each targeting a measured failure mode:

  1. COMBINE real data: reward-filtered sessions (210->vindicated) + replay (481 real
     outcomes) = the full real-outcome corpus. More signal, more coverage.

  2. STRIP IDENTITY: remove literal `wallet:`/`token_mint:` address lines from the
     prompt. The replay corpus is concentrated in 9 tokens; with addresses present the
     model can memorize "token X = loss" instead of learning from features. Stripping
     forces feature-based reasoning -> better out-of-sample generalization.

  3. BALANCE CLASSES: cap no_trade to ~1.3x signal count so the model does not collapse
     to always-no_trade (the v2 failure mode on the 40-sample).

Inputs (already on disk):
  finetune/data/training/_replay_all.jsonl          (481 replay SFT examples)
  finetune/data/training/train_rewardfiltered.jsonl (133 weighted session examples)
  finetune/data/training/val_rewardfiltered.jsonl   (11 session examples)

Output: train_v4.jsonl / val_v4.jsonl
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "finetune" / "data" / "training"
REPLAY = OUT / "_replay_all.jsonl"
SESS_TRAIN = OUT / "train_rewardfiltered.jsonl"
SESS_VAL = OUT / "val_rewardfiltered.jsonl"
TRAIN_V4 = OUT / "train_v4.jsonl"
VAL_V4 = OUT / "val_v4.jsonl"

NOTRADE_RATIO = 1.3   # max no_trade per signal
VAL_SPLIT = 0.15
random.seed(2026)

_WALLET_LINE = re.compile(r'^\s*wallet:\s*\S+\s*$', re.MULTILINE)
_TOKEN_LINE = re.compile(r'^\s*token_mint:\s*\S+\s*$', re.MULTILINE)


def strip_identity(example: dict) -> dict:
    """Remove literal wallet/token address lines from the user prompt."""
    user = example["contents"][0]["parts"][0]["text"]
    user = _WALLET_LINE.sub("", user)
    user = _TOKEN_LINE.sub("", user)
    # also scrub token_mint / symbol keys inside evidence JSON lines
    user = re.sub(r'"token_mint":\s*"[^"]*",?\s*', "", user)
    user = re.sub(r'"symbol":\s*"[^"]*",?\s*', "", user)
    user = re.sub(r'\n{3,}', "\n\n", user)
    example["contents"][0]["parts"][0]["text"] = user
    return example


def decision_of(example: dict) -> str:
    try:
        mt = example["contents"][1]["parts"][0]["text"]
        return json.loads(mt).get("decision_type", "no_trade")
    except Exception:
        return "no_trade"


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def main() -> None:
    raw = load(REPLAY) + load(SESS_TRAIN) + load(SESS_VAL)
    print(f"[v4] loaded raw examples: {len(raw)}")

    # strip identity
    examples = [strip_identity(e) for e in raw]

    signals = [e for e in examples if decision_of(e) == "signal"]
    notrades = [e for e in examples if decision_of(e) != "signal"]
    print(f"[v4] signals={len(signals)} no_trades={len(notrades)}")

    # balance: cap no_trade
    random.shuffle(notrades)
    cap = max(10, int(len(signals) * NOTRADE_RATIO))
    notrades = notrades[:cap]
    print(f"[v4] no_trade capped to {len(notrades)} (ratio {NOTRADE_RATIO})")

    pool = signals + notrades
    random.shuffle(pool)

    val_n = max(4, int(len(pool) * VAL_SPLIT))
    val = pool[:val_n]
    train = pool[val_n:]

    TRAIN_V4.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in train), encoding="utf-8")
    VAL_V4.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in val), encoding="utf-8")

    print(f"[v4] TRAIN={len(train)} VAL={len(val)}")
    print(f"[v4] train decisions: {dict(Counter(decision_of(e) for e in train))}")
    print(f"[v4] val decisions:   {dict(Counter(decision_of(e) for e in val))}")
    # show a stripped sample
    print("\n[v4] sample user (identity stripped):")
    print(train[0]["contents"][0]["parts"][0]["text"][:380])


if __name__ == "__main__":
    main()
