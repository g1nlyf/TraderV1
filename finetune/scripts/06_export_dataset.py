"""
Script 06: Export labeled sessions as JSONL training dataset.

Reads session files from data/sessions/*.json
Filters by outcome_label
Converts to OpenAI fine-tuning JSONL format
Writes train.jsonl and val.jsonl to data/training/

Usage:
  python scripts/06_export_dataset.py
  python scripts/06_export_dataset.py --include-unlabeled  # include sessions without outcome labels
  python scripts/06_export_dataset.py --min-quality good   # only "good" and "excellent"
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "finetune"))

SESSIONS_DIR = ROOT / "finetune" / "data" / "sessions"
TRAIN_FILE = ROOT / "finetune" / "data" / "training" / "train.jsonl"
VAL_FILE = ROOT / "finetune" / "data" / "training" / "val.jsonl"
TOOLS_FILE = ROOT / "finetune" / "config" / "tools.json"

TOOLS = json.loads(TOOLS_FILE.read_text(encoding="utf-8"))

# Gemini-format tools (converted from OpenAI format for Vertex SFT)
# OpenAI: [{type, function: {name, description, parameters}}]
# Gemini: [{function_declarations: [{name, description, parameters}]}]
# Vertex SFT requires schema `type` values to be UPPERCASE (STRING, OBJECT, etc.)
def _uppercase_schema_types(schema: dict) -> dict:
    """Recursively convert JSON Schema `type` values to uppercase for Vertex AI."""
    if not isinstance(schema, dict):
        return schema
    result = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            result[k] = v.upper()
        elif isinstance(v, dict):
            result[k] = _uppercase_schema_types(v)
        elif isinstance(v, list):
            result[k] = [_uppercase_schema_types(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result


TOOLS_GEMINI = [
    {
        "function_declarations": [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "parameters": _uppercase_schema_types(t["function"].get("parameters", {})),
            }
            for t in TOOLS
            if t.get("type") == "function"
        ]
    }
]

# Quality label tiers
POSITIVE_LABELS = {"excellent", "good", "good_no_trade"}
NEGATIVE_LABELS = {"loss", "bad_no_trade"}
NEUTRAL_LABELS = {"marginal", "neutral_no_trade"}

# Weight for sampling (higher = more likely to include)
LABEL_WEIGHTS = {
    "excellent": 3.0,
    "good": 2.0,
    "good_no_trade": 1.5,
    "marginal": 0.5,
    "neutral_no_trade": 0.3,
    "loss": 1.0,       # Include losses as negative examples
    "bad_no_trade": 1.0,
    "unlabeled": 0.8,  # Include if --include-unlabeled
}


def session_to_training_example(session: dict) -> dict | None:
    """Convert a teacher session to OpenAI fine-tuning format."""
    messages = session.get("messages")
    if not messages:
        return None

    training_messages = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            training_messages.append(msg)
            continue
        if role == "user":
            training_messages.append({"role": "user", "content": msg.get("content", "")})
            continue
        if role == "assistant":
            cleaned = {"role": "assistant"}
            if msg.get("content"):
                cleaned["content"] = msg["content"]
            if msg.get("tool_calls"):
                cleaned["tool_calls"] = msg["tool_calls"]
            training_messages.append(cleaned)
            continue
        if role == "tool":
            training_messages.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id", ""),
                "content": msg.get("content", ""),
            })
            continue

    if len(training_messages) < 4:
        return None

    has_decision = any(
        fn.get("name") == "agent_record_trading_decision"
        for msg in training_messages
        if msg.get("role") == "assistant"
        for tc in (msg.get("tool_calls") or [])
        for fn in [tc.get("function", {})]
    )
    if not has_decision:
        return None

    return {"messages": training_messages, "tools": TOOLS}


def _openai_msgs_to_gemini(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Convert OpenAI message list → (system_str, gemini_contents) for Vertex SFT."""
    system = None
    contents = []
    id_to_name: dict[str, str] = {}

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            system = msg.get("content") or ""
        elif role == "user":
            text = msg.get("content") or ""
            if text:
                contents.append({"role": "user", "parts": [{"text": text}]})
        elif role == "assistant":
            parts = []
            if msg.get("content"):
                parts.append({"text": msg["content"]})
            for tc in (msg.get("tool_calls") or []):
                fn = tc["function"]
                try:
                    args = json.loads(fn["arguments"])
                except Exception:
                    args = {}
                id_to_name[tc["id"]] = fn["name"]
                parts.append({"functionCall": {"name": fn["name"], "args": args}})
            if parts:
                contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            fn_name = id_to_name.get(msg.get("tool_call_id", ""), "tool_result")
            try:
                content = json.loads(msg["content"])
            except Exception:
                content = {"text": str(msg.get("content", ""))}
            contents.append({
                "role": "user",
                "parts": [{"functionResponse": {"name": fn_name, "response": content}}],
            })

    return system, contents


def session_to_gemini_example(session: dict) -> dict | None:
    """Convert a teacher session to Vertex AI Gemini SFT format (contents array)."""
    messages = session.get("messages")
    if not messages:
        return None

    # Validate decision present
    has_decision = any(
        fn.get("name") == "agent_record_trading_decision"
        for msg in messages
        if msg.get("role") == "assistant"
        for tc in (msg.get("tool_calls") or [])
        for fn in [tc.get("function", {})]
    )
    if not has_decision:
        return None

    system, contents = _openai_msgs_to_gemini(messages)
    if len(contents) < 3:
        return None

    # Vertex SFT requires the last turn to be role=model.
    # Our sessions end with a functionResponse (role=user). Add a closing model turn.
    if contents and contents[-1].get("role") == "user":
        # Determine session type from decision
        decision_type = session.get("decision_type", "")
        if not decision_type:
            # Infer from messages
            for msg in messages:
                if msg.get("role") == "assistant":
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function", {})
                        if fn.get("name") == "agent_record_trading_decision":
                            try:
                                args = json.loads(fn.get("arguments", "{}"))
                                decision_type = args.get("decision_type", "")
                            except Exception:
                                pass

        if decision_type == "signal":
            closing_text = "Trading session complete. Signal executed and position opened."
        else:
            closing_text = "Analysis complete. No trade taken for this signal."

        contents.append({"role": "model", "parts": [{"text": closing_text}]})

    example: dict = {"contents": contents, "tools": TOOLS_GEMINI}
    if system:
        example["systemInstruction"] = {"parts": [{"text": system}]}
    return example


def export_dataset(
    include_unlabeled: bool = False,
    min_quality: str = "all",
    val_split: float = 0.15,
    fmt: str = "vertex",  # "openai" | "vertex"
) -> None:
    """Export sessions as JSONL.

    fmt="vertex"  → Gemini contents format for Vertex AI SFT (default)
    fmt="openai"  → OpenAI messages format for OpenAI fine-tuning
    """
    session_files = sorted(SESSIONS_DIR.glob("*.json"))
    if not session_files:
        print(f"[export] No session files in {SESSIONS_DIR}")
        return

    print(f"[export] Found {len(session_files)} session files  (format={fmt})")

    examples = []
    skipped = 0

    for sf in session_files:
        try:
            session = json.loads(sf.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[export] SKIP {sf.name}: {exc}")
            skipped += 1
            continue

        label = session.get("outcome_label")

        if not include_unlabeled and label in (None, "unlabeled", "pending"):
            skipped += 1
            continue

        if min_quality == "good" and label not in POSITIVE_LABELS:
            skipped += 1
            continue

        if session.get("dry_run"):
            skipped += 1
            continue

        if fmt == "vertex":
            example = session_to_gemini_example(session)
        else:
            example = session_to_training_example(session)

        if not example:
            skipped += 1
            continue

        examples.append((example, label))

    print(f"[export] Valid examples: {len(examples)} (skipped: {skipped})")

    if not examples:
        print("[export] No examples to export. Use --include-unlabeled or add outcome labels.")
        return

    if len(examples) < 10:
        print(f"[export] WARNING: Only {len(examples)} examples — need >=10, ideally 100+.")

    # Apply label weights: oversample high-quality examples by repeating them
    weighted_examples = []
    for ex, label in examples:
        weight = LABEL_WEIGHTS.get(label or "unlabeled", 0.8)
        # Fractional repeat: weight=3.0 → 3 copies, weight=0.5 → 50% chance of inclusion
        full_copies = int(weight)
        for _ in range(full_copies):
            weighted_examples.append((ex, label))
        if random.random() < (weight - full_copies):
            weighted_examples.append((ex, label))

    random.shuffle(weighted_examples)

    # Val split drawn from unweighted examples to avoid duplicates in val
    random.shuffle(examples)
    val_size = max(1, int(len(examples) * val_split))
    val_examples = [e for e, _ in examples[:val_size]]

    # Train uses weighted set minus val tokens (val is always from original unweighted)
    val_set = set(id(e) for e, _ in examples[:val_size])
    train_examples = [e for e, l in weighted_examples]  # all weighted, no dedup needed

    from collections import Counter
    label_counts = Counter(label for _, label in examples)
    train_label_counts = Counter(label for _, label in weighted_examples)
    print(f"[export] Label distribution (raw): {dict(label_counts)}")
    print(f"[export] Label distribution (weighted train): {dict(train_label_counts)}")
    print(f"[export] Train: {len(train_examples)} (weighted) | Val: {len(val_examples)} (unweighted)")

    # File names differ by format
    if fmt == "vertex":
        train_out = TRAIN_FILE.parent / "train_vertex.jsonl"
        val_out = TRAIN_FILE.parent / "val_vertex.jsonl"
    else:
        train_out = TRAIN_FILE
        val_out = VAL_FILE

    train_out.parent.mkdir(parents=True, exist_ok=True)

    with train_out.open("w", encoding="utf-8") as f:
        for ex in train_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    with val_out.open("w", encoding="utf-8") as f:
        for ex in val_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"[export] Written: {train_out.relative_to(ROOT)}")
    print(f"[export] Written: {val_out.relative_to(ROOT)}")
    print("[export] Run scripts/07_train.py to submit fine-tuning job.")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Export training dataset")
    parser.add_argument("--include-unlabeled", action="store_true")
    parser.add_argument("--min-quality", choices=["all", "good"], default="all")
    parser.add_argument("--val-split", type=float, default=0.15)
    parser.add_argument("--format", choices=["vertex", "openai"], default="vertex",
                        dest="fmt", help="Output format: vertex (Gemini) or openai")
    args = parser.parse_args()
    export_dataset(
        include_unlabeled=args.include_unlabeled,
        min_quality=args.min_quality,
        val_split=args.val_split,
        fmt=args.fmt,
    )


if __name__ == "__main__":
    main()
