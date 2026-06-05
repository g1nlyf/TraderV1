"""
Convert agentic multi-turn JSONL (with functionCall/functionResponse) to
clean text-to-text format for Vertex AI SFT.

Input format: multi-turn conversation with tool calls
Output format: single user turn (context + all fetched data) → model decision JSON

Run:
  python finetune/scripts/convert_agentic_to_text.py
"""
from __future__ import annotations
import json, sys, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[2]
TRAIN_IN  = ROOT / "finetune/data/training/train_vertex.jsonl"
VAL_IN    = ROOT / "finetune/data/training/val_vertex.jsonl"
TRAIN_OUT = ROOT / "finetune/data/training/train_sft.jsonl"
VAL_OUT   = ROOT / "finetune/data/training/val_sft.jsonl"


def extract_text(parts: list) -> str:
    return " ".join(p["text"] for p in parts if "text" in p).strip()


def extract_fn_args(parts: list, fn_name: str) -> dict | None:
    for p in parts:
        if "functionCall" in p and p["functionCall"]["name"] == fn_name:
            return p["functionCall"].get("args", {})
    return None


def extract_fn_response(parts: list, fn_name: str) -> dict | None:
    for p in parts:
        if "functionResponse" in p and p["functionResponse"]["name"] == fn_name:
            return p["functionResponse"].get("response", {})
    return None


def convert_example(ex: dict) -> dict | None:
    contents = ex.get("contents", [])

    # Collect data from all turns
    signal_context = ""
    wallet_data: dict = {}
    token_data: dict = {}
    market_data: dict = {}
    decision_args: dict = {}
    final_text = ""

    for c in contents:
        role = c.get("role", "")
        parts = c.get("parts", [])

        if role == "user":
            txt = extract_text(parts)
            if txt and not signal_context:
                signal_context = txt

            # Tool responses come as user turns
            wr = extract_fn_response(parts, "wallet_profile_history")
            if wr:
                wallet_data = wr.get("profile", wr)

            tr = extract_fn_response(parts, "token_get_profile")
            if tr:
                token_data = tr.get("profile", tr)

            mr = extract_fn_response(parts, "market_get_token_snapshot")
            if mr:
                market_data = mr.get("snapshot", mr)

        elif role == "model":
            # Capture decision
            da = extract_fn_args(parts, "agent_record_trading_decision")
            if da:
                decision_args = da

            # Final text summary
            txt = extract_text(parts)
            if txt:
                final_text = txt

    if not signal_context or not decision_args:
        return None

    # Build consolidated user prompt
    lines = [signal_context]

    if wallet_data:
        lines.append("\n--- WALLET PROFILE ---")
        lines.append(json.dumps(wallet_data, ensure_ascii=False))

    if token_data:
        lines.append("\n--- TOKEN PROFILE ---")
        lines.append(json.dumps(token_data, ensure_ascii=False))

    if market_data:
        lines.append("\n--- MARKET SNAPSHOT ---")
        lines.append(json.dumps(market_data, ensure_ascii=False))

    user_prompt = "\n".join(lines)

    # Build model output: structured decision JSON
    model_output = json.dumps(decision_args, ensure_ascii=False, indent=2)

    return {
        "contents": [
            {"role": "user",  "parts": [{"text": user_prompt}]},
            {"role": "model", "parts": [{"text": model_output}]},
        ]
    }


def convert_file(in_path: pathlib.Path, out_path: pathlib.Path) -> int:
    ok = 0
    skipped = 0
    with in_path.open(encoding="utf-8") as fin, \
         out_path.open("w", encoding="utf-8") as fout:
        for i, line in enumerate(fin, 1):
            line = line.strip()
            if not line:
                continue
            ex = json.loads(line)
            converted = convert_example(ex)
            if converted is None:
                skipped += 1
                print(f"  SKIP line {i}: no signal_context or decision_args")
                continue
            fout.write(json.dumps(converted, ensure_ascii=False) + "\n")
            ok += 1
    print(f"  {in_path.name}: {ok} converted, {skipped} skipped → {out_path.name}")
    return ok


def main():
    print("Converting agentic JSONL -> text-to-text SFT format")
    print()

    for in_path, out_path in [(TRAIN_IN, TRAIN_OUT), (VAL_IN, VAL_OUT)]:
        if not in_path.exists():
            print(f"  SKIP (not found): {in_path}")
            continue
        convert_file(in_path, out_path)

    # Show sample
    print()
    print("=== Sample converted example ===")
    with TRAIN_OUT.open(encoding="utf-8") as f:
        sample = json.loads(f.readline())
    user_text = sample["contents"][0]["parts"][0]["text"]
    model_text = sample["contents"][1]["parts"][0]["text"]
    print(f"USER ({len(user_text)} chars):\n{user_text[:600]}...")
    print(f"\nMODEL:\n{model_text}")


if __name__ == "__main__":
    main()
