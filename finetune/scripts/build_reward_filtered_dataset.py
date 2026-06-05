"""
Reward-Filtered Dataset Builder (Outcome-as-Teacher, idea #1).

THE PIVOT: v1 cloned ALL decisions including the 33 that lost money.
v2 clones ONLY decisions the market vindicated:
  - signal + excellent/good   -> KEEP (good trade)
  - signal + marginal         -> KEEP low weight
  - signal + loss             -> DROP (do not clone bad trades) -> saved for future DPO
  - no_trade + good_no_trade  -> KEEP high (correctly avoided)
  - no_trade + neutral        -> KEEP, capped (don't let skips drown signals)
  - no_trade + bad_no_trade   -> DROP (wrongly skipped a winner)

Output: text-to-text Gemini SFT format (the only format Vertex accepts;
agentic functionCall format fails with "unsupported modality").

  user  = signal context + consolidated tool evidence (REAL data, point-in-time)
  model = decision JSON {decision_type, confidence, pre_action_reasoning}

Dropped losses are written to losses_for_dpo.jsonl (rejected side of future DPO pairs).

Run:
  python finetune/scripts/build_reward_filtered_dataset.py
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = ROOT / "finetune" / "data" / "sessions"
OUT_DIR = ROOT / "finetune" / "data" / "training"
PROMPTS_DIR = ROOT / "finetune" / "prompts"

TRAIN_OUT = OUT_DIR / "train_rewardfiltered.jsonl"
VAL_OUT = OUT_DIR / "val_rewardfiltered.jsonl"
DPO_OUT = OUT_DIR / "losses_for_dpo.jsonl"

SYSTEM_PROMPT = (PROMPTS_DIR / "teacher_system.md").read_text(encoding="utf-8")

# Outcome-as-teacher: weight = how many times to replicate a vindicated decision.
# DROP_LABELS are never cloned (bad decisions) — saved separately for DPO.
KEEP_WEIGHTS = {
    "excellent": 4,        # signal that mooned (>=1.20x)
    "good": 3,             # signal that did well (>=1.08x)
    "good_no_trade": 3,    # correctly avoided a flat/loser
    "marginal": 1,         # signal ~flat — weak positive
    "neutral_no_trade": 1, # skipped, was flat — fine but capped below
}
DROP_LABELS = {"loss", "bad_no_trade", None, "unlabeled", "pending"}

# Cap neutral_no_trade so skips don't drown signal examples.
# Set to ~1.5x the count of kept signal examples (computed at runtime).
NEUTRAL_CAP_RATIO = 1.5

VAL_SPLIT = 0.15
random.seed(1337)


# ── extraction ──────────────────────────────────────────────────────────────────

def _id_to_name(messages: list[dict]) -> dict[str, str]:
    m: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                m[tc.get("id", "")] = tc.get("function", {}).get("name", "")
    return m


def _tool_result(messages: list[dict], id2name: dict, name: str) -> dict | None:
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        if id2name.get(msg.get("tool_call_id", "")) == name:
            try:
                return json.loads(msg.get("content") or "{}")
            except Exception:
                return None
    return None


def _assistant_call_args(messages: list[dict], name: str) -> dict | None:
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if tc.get("function", {}).get("name") == name:
                try:
                    return json.loads(tc["function"].get("arguments") or "{}")
                except Exception:
                    return None
    return None


def _first_user_context(messages: list[dict]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            return msg.get("content") or ""
    return ""


def build_example(session: dict) -> dict | None:
    """Convert one session -> text-to-text Gemini SFT example (real data only)."""
    messages = session.get("messages") or []
    id2name = _id_to_name(messages)

    ctx = _first_user_context(messages)
    if not ctx:
        return None
    # Replace the agentic trailing instruction with a text-to-text instruction.
    ctx = ctx.split("Execute the required tool sequence")[0].rstrip()

    wallet = _tool_result(messages, id2name, "wallet_profile_history") or {}
    token = _tool_result(messages, id2name, "token_get_profile") or {}
    market = _tool_result(messages, id2name, "market_get_token_snapshot") or {}

    decision = _assistant_call_args(messages, "agent_record_trading_decision")
    if not decision:
        return None
    sig = _assistant_call_args(messages, "signal_create") or {}

    wallet_profile = wallet.get("profile", wallet)
    token_profile = token.get("profile", token)
    market_snapshot = market.get("snapshot", market)

    # ── user prompt: signal + consolidated REAL evidence ─────────────────────────
    parts = [ctx, "\nEVIDENCE:"]
    if wallet_profile:
        parts.append("--- WALLET PROFILE ---")
        parts.append(json.dumps(wallet_profile, ensure_ascii=False))
    if token_profile:
        parts.append("--- TOKEN PROFILE ---")
        parts.append(json.dumps(token_profile, ensure_ascii=False))
    if market_snapshot:
        parts.append("--- MARKET SNAPSHOT ---")
        parts.append(json.dumps(market_snapshot, ensure_ascii=False))
    parts.append("\nReview the evidence and output your decision as JSON "
                 "with keys: decision_type, confidence, pre_action_reasoning.")
    user_text = "\n".join(parts)

    # ── model output: decision JSON ──────────────────────────────────────────────
    out = {
        "decision_type": decision.get("decision_type"),
        "confidence": sig.get("confidence"),  # null for no_trade
        "pre_action_reasoning": decision.get("pre_action_reasoning", ""),
    }
    model_text = json.dumps(out, ensure_ascii=False, indent=2)

    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {"role": "user", "parts": [{"text": user_text}]},
            {"role": "model", "parts": [{"text": model_text}]},
        ],
    }


# ── main ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    files = sorted(SESSIONS_DIR.glob("*.json"))
    print(f"[build] {len(files)} session files")

    kept: list[tuple[dict, str]] = []   # (example, label)
    neutrals: list[dict] = []
    dropped_losses: list[dict] = []
    raw_labels = Counter()

    for sf in files:
        try:
            session = json.loads(sf.read_text(encoding="utf-8"))
        except Exception:
            continue
        label = session.get("outcome_label")
        raw_labels[label] += 1

        if label in DROP_LABELS:
            # Save losses for future DPO (rejected side).
            if label in ("loss", "bad_no_trade"):
                ex = build_example(session)
                if ex:
                    dropped_losses.append({"label": label, "example": ex})
            continue

        ex = build_example(session)
        if not ex:
            continue

        if label == "neutral_no_trade":
            neutrals.append(ex)
        else:
            kept.append((ex, label))

    # Count signal examples to cap neutrals proportionally.
    n_signal = sum(1 for _, lbl in kept if lbl in ("excellent", "good", "marginal"))
    neutral_cap = max(10, int(n_signal * NEUTRAL_CAP_RATIO))
    random.shuffle(neutrals)
    capped_neutrals = neutrals[:neutral_cap]
    for ex in capped_neutrals:
        kept.append((ex, "neutral_no_trade"))

    print(f"[build] raw labels: {dict(raw_labels)}")
    print(f"[build] signal examples kept: {n_signal}")
    print(f"[build] neutral_no_trade: {len(neutrals)} -> capped {len(capped_neutrals)}")
    print(f"[build] losses saved for DPO: {len(dropped_losses)}")
    print(f"[build] total kept (pre-weight): {len(kept)}")

    # ── val split from unweighted kept ──────────────────────────────────────────
    random.shuffle(kept)
    val_n = max(2, int(len(kept) * VAL_SPLIT))
    val = kept[:val_n]
    train_src = kept[val_n:]

    # ── apply reward weights (replicate vindicated decisions) ────────────────────
    train: list[dict] = []
    for ex, label in train_src:
        w = KEEP_WEIGHTS.get(label, 1)
        train.extend([ex] * w)
    random.shuffle(train)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with TRAIN_OUT.open("w", encoding="utf-8") as f:
        for ex in train:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    with VAL_OUT.open("w", encoding="utf-8") as f:
        for ex, _ in val:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    with DPO_OUT.open("w", encoding="utf-8") as f:
        for d in dropped_losses:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"[build] TRAIN: {len(train)} (weighted) -> {TRAIN_OUT.name}")
    print(f"[build] VAL:   {len(val)} -> {VAL_OUT.name}")
    print(f"[build] DPO losses: {len(dropped_losses)} -> {DPO_OUT.name}")

    # Sanity: show one example
    if train:
        print("\n=== sample ===")
        s = train[0]
        print("USER:", s["contents"][0]["parts"][0]["text"][:400])
        print("MODEL:", s["contents"][1]["parts"][0]["text"][:300])


if __name__ == "__main__":
    main()
