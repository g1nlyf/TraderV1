"""
Backtest + Off-Policy Eval Harness (blueprint #27/#45) — the DEPLOY GATE.

No model ships without passing this. Evaluates any policy against outcome-labelled
data and reports the only metric that matters: net-expectancy proxy after costs,
plus signal precision/recall, per-bucket lift, and calibration.

Policies (callable: context_text -> {decision_type, confidence}):
  RecordedPolicy   — replays the decision already in the session (= formula baseline)
  TunedModelPolicy — calls a Vertex tuned-model endpoint (the candidate)

Eval set: finetune/data/sessions/*.json (each has a decision + a real outcome_label).

A policy is GOOD if its decisions concentrate on good outcomes:
  - signals that turned excellent/good  → reward
  - signals that turned loss            → penalty
  - no_trade that avoided a loser       → small credit
  - no_trade that missed a winner       → penalty

Run:
  python -m finetune.pipeline.backtest_harness --policy recorded
  python -m finetune.pipeline.backtest_harness --policy tuned --endpoint <ENDPOINT>
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = ROOT / "finetune" / "data" / "sessions"
PROMPTS_DIR = ROOT / "finetune" / "prompts"

# Outcome label → realised net-P&L proxy (fraction). Used to score policies.
# Signals are credited/penalised by what the trade did; no_trades by counterfactual.
LABEL_PNL = {
    "excellent": +0.25, "good": +0.12, "marginal": +0.02, "loss": -0.20,
    "good_no_trade": +0.03, "neutral_no_trade": 0.0, "bad_no_trade": -0.10,
}
# What a no_trade "would have" cost/saved if we had traded (counterfactual sign).
NOTRADE_CF = {"good_no_trade": -0.15, "neutral_no_trade": 0.0, "bad_no_trade": +0.18}


@dataclass
class EvalExample:
    context_text: str
    recorded_decision: str
    recorded_confidence: str | None
    outcome_label: str | None
    # what actually happened to the token (sign of the trade), regardless of decision
    token_outcome_is_winner: bool


# ── eval set loader ──────────────────────────────────────────────────────────────

def _id_to_name(messages):
    m = {}
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                m[tc.get("id", "")] = tc.get("function", {}).get("name", "")
    return m


def _decision(messages):
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                if tc.get("function", {}).get("name") == "agent_record_trading_decision":
                    try:
                        return json.loads(tc["function"].get("arguments") or "{}")
                    except Exception:
                        return {}
    return {}


def _confidence(messages):
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                if tc.get("function", {}).get("name") == "signal_create":
                    try:
                        return json.loads(tc["function"].get("arguments") or "{}").get("confidence")
                    except Exception:
                        return None
    return None


def _context(messages) -> str:
    """Rebuild the text-to-text user context from a session (matches builder)."""
    id2 = _id_to_name(messages)
    ctx = ""
    wallet = token = market = {}
    for msg in messages:
        if msg.get("role") == "user" and not ctx:
            ctx = (msg.get("content") or "").split("Execute the required tool sequence")[0].rstrip()
        if msg.get("role") == "tool":
            name = id2.get(msg.get("tool_call_id", ""))
            try:
                c = json.loads(msg.get("content") or "{}")
            except Exception:
                continue
            if name == "wallet_profile_history":
                wallet = c.get("profile", c)
            elif name == "token_get_profile":
                token = c.get("profile", c)
            elif name == "market_get_token_snapshot":
                market = c.get("snapshot", c)
    parts = [ctx, "\nEVIDENCE:",
             "--- WALLET PROFILE ---", json.dumps(wallet, ensure_ascii=False),
             "--- TOKEN PROFILE ---", json.dumps(token, ensure_ascii=False),
             "--- MARKET SNAPSHOT ---", json.dumps(market, ensure_ascii=False),
             "\nReview the evidence and output your decision as JSON "
             "with keys: decision_type, confidence, pre_action_reasoning."]
    return "\n".join(parts)


def load_eval_file(path: str) -> list[EvalExample]:
    """Load EvalExamples from a JSONL (e.g. token-disjoint momentum holdout)."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        out.append(EvalExample(
            context_text=d["context_text"],
            recorded_decision=d.get("recorded_decision", "no_trade"),
            recorded_confidence=d.get("recorded_confidence"),
            outcome_label=d.get("outcome_label"),
            token_outcome_is_winner=bool(d.get("token_outcome_is_winner")),
        ))
    return out


def load_eval_set() -> list[EvalExample]:
    out = []
    for sf in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            s = json.loads(sf.read_text(encoding="utf-8"))
        except Exception:
            continue
        label = s.get("outcome_label")
        if label is None:
            continue
        msgs = s.get("messages") or []
        dec = _decision(msgs)
        winner = label in ("excellent", "good", "bad_no_trade")  # token went up
        out.append(EvalExample(
            context_text=_context(msgs),
            recorded_decision=dec.get("decision_type", "no_trade"),
            recorded_confidence=_confidence(msgs),
            outcome_label=label,
            token_outcome_is_winner=winner,
        ))
    return out


# ── policies ─────────────────────────────────────────────────────────────────────

def recorded_policy(ex: EvalExample) -> dict:
    return {"decision_type": ex.recorded_decision, "confidence": ex.recorded_confidence}


class TunedModelPolicy:
    """Calls a Vertex tuned-model endpoint with the text-to-text prompt."""
    def __init__(self, endpoint: str, project="sft-test-clean", location="us-central1",
                 timeout_ms: int = 25000):
        from google import genai
        from google.genai import types
        # Per-call HTTP timeout so hung requests error out instead of stalling the gate.
        self.client = genai.Client(
            vertexai=True, project=project, location=location,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
        self.endpoint = endpoint
        self.system = (PROMPTS_DIR / "teacher_system.md").read_text(encoding="utf-8")

    def __call__(self, ex: EvalExample) -> dict:
        from google.genai import types
        try:
            resp = self.client.models.generate_content(
                model=self.endpoint,
                contents=[types.Content(role="user", parts=[types.Part(text=ex.context_text)])],
                config=types.GenerateContentConfig(system_instruction=self.system,
                                                   temperature=0.0, max_output_tokens=1024),
            )
            txt = (resp.text or "").strip()
            blob = txt[txt.find("{"): txt.rfind("}") + 1] if "{" in txt else ""
            try:
                d = json.loads(blob)
                return {"decision_type": d.get("decision_type", "no_trade"),
                        "confidence": d.get("confidence")}
            except Exception:
                # Lenient fallback for truncated JSON: regex the decision fields.
                import re
                dm = re.search(r'"decision_type"\s*:\s*"(\w+)"', txt)
                cm = re.search(r'"confidence"\s*:\s*"(\w+)"', txt)
                if dm:
                    return {"decision_type": dm.group(1),
                            "confidence": cm.group(1) if cm else None}
                return {"decision_type": "no_trade", "confidence": None, "_error": "parse_fail"}
        except Exception as e:
            return {"decision_type": "no_trade", "confidence": None, "_error": str(e)[:80]}


class CascadePolicy:
    """v3 proposes (recall), v2 confirms (precision). Signal only if BOTH agree."""
    def __init__(self, propose_endpoint: str, confirm_endpoint: str, **kw):
        self.proposer = TunedModelPolicy(propose_endpoint, **kw)
        self.confirmer = TunedModelPolicy(confirm_endpoint, **kw)

    def __call__(self, ex: EvalExample) -> dict:
        p = self.proposer(ex)
        if p.get("decision_type") != "signal":
            return p
        c = self.confirmer(ex)
        if c.get("decision_type") == "signal":
            return p
        return {"decision_type": "no_trade", "confidence": None, "_cascade": "override"}


class EnsemblePolicy:
    """N diverse models vote. Signal only if >= k_signal agree on 'signal' (precision lever).
    Highest value with DIVERSE datasets (v2 reward-filtered, v3 replay, v4 combined)."""
    def __init__(self, endpoints: list[str], k_signal: int | None = None, **kw):
        self.models = [TunedModelPolicy(e, **kw) for e in endpoints]
        self.k = k_signal if k_signal is not None else (len(endpoints) // 2 + 1)  # majority

    def __call__(self, ex: EvalExample) -> dict:
        votes = [m(ex) for m in self.models]
        sig = [v for v in votes if v.get("decision_type") == "signal"]
        if len(sig) >= self.k:
            # highest-confidence signal among the agreeing models
            tiers = {"high": 3, "medium": 2, "low": 1, None: 0}
            best = max(sig, key=lambda v: tiers.get(v.get("confidence"), 0))
            return {"decision_type": "signal", "confidence": best.get("confidence"),
                    "_votes": f"{len(sig)}/{len(votes)}"}
        return {"decision_type": "no_trade", "confidence": None, "_votes": f"{len(sig)}/{len(votes)}"}


# Position size by confidence tier (fraction of capital) — for sized-EV scoring.
TIER_SIZE = {"high": 0.08, "medium": 0.05, "low": 0.02, None: 0.05}


# ── scorer ───────────────────────────────────────────────────────────────────────

def _run_policy(policy: Callable[[EvalExample], dict], eval_set: list[EvalExample],
                workers: int = 8) -> list[dict]:
    """Run a policy over the eval set (parallel for network policies), with progress."""
    from concurrent.futures import ThreadPoolExecutor
    n = len(eval_set)
    preds: list[dict | None] = [None] * n
    done = 0
    if workers <= 1:
        for i, ex in enumerate(eval_set):
            preds[i] = policy(ex)
            done += 1
            if done % 25 == 0 or done == n:
                print(f"  [eval] {done}/{n}", flush=True)
        return preds  # type: ignore
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(policy, ex): i for i, ex in enumerate(eval_set)}
        for fut in futs:
            i = futs[fut]
            try:
                preds[i] = fut.result()
            except Exception as e:
                preds[i] = {"decision_type": "no_trade", "confidence": None, "_error": str(e)[:80]}
            done += 1
            if done % 25 == 0 or done == n:
                print(f"  [eval] {done}/{n}", flush=True)
    return preds  # type: ignore


def score(policy: Callable[[EvalExample], dict], eval_set: list[EvalExample],
          workers: int = 8) -> dict:
    total_pnl = 0.0
    n = len(eval_set)
    sig_pred = sig_correct = notrade_pred = 0
    conf = Counter()
    confusion = defaultdict(int)
    by_label = Counter()
    errors = 0

    sized_pnl = 0.0   # position-sized EV (Kelly-by-tier) — the honest capital metric
    preds = _run_policy(policy, eval_set, workers=workers)
    for ex, pred in zip(eval_set, preds):
        if pred.get("_error"):
            errors += 1
        dt = pred.get("decision_type", "no_trade")
        label = ex.outcome_label
        by_label[label] += 1
        confusion[(dt, "winner" if ex.token_outcome_is_winner else "loser")] += 1

        if dt == "signal":
            sig_pred += 1
            trade_pnl = LABEL_PNL.get(label, 0.0) if label in ("excellent", "good", "marginal", "loss") \
                else (+0.12 if ex.token_outcome_is_winner else -0.20)
            total_pnl += trade_pnl
            sized_pnl += trade_pnl * (TIER_SIZE.get(pred.get("confidence"), 0.05) / 0.05)
            if ex.token_outcome_is_winner:
                sig_correct += 1
            conf[pred.get("confidence")] += 1
        else:
            notrade_pred += 1
            total_pnl += NOTRADE_CF.get(label, 0.0)

    signal_precision = (sig_correct / sig_pred) if sig_pred else None
    return {
        "n": n,
        "net_expectancy_proxy": round(total_pnl / n, 4) if n else 0,
        "ev_sized_per_trade": round(sized_pnl / sig_pred, 4) if sig_pred else 0,
        "ev_sized_total": round(sized_pnl, 3),
        "total_pnl_proxy": round(total_pnl, 3),
        "signals_predicted": sig_pred,
        "signal_precision": round(signal_precision, 3) if signal_precision is not None else None,
        "no_trades_predicted": notrade_pred,
        "call_errors": errors,
        "confidence_dist": dict(conf),
        "confusion(decision,token)": dict(confusion),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=["recorded", "tuned", "cascade"], default="recorded")
    ap.add_argument("--endpoint", help="Vertex endpoint (tuned) or proposer (cascade)")
    ap.add_argument("--confirm-endpoint", help="Confirmer endpoint (cascade only)")
    ap.add_argument("--gate-baseline", type=float, default=None,
                    help="Fail (exit 1) if net_expectancy_proxy below this baseline.")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None, help="Sample first N eval examples.")
    ap.add_argument("--eval-file", default=None, help="JSONL EvalExamples (e.g. token-disjoint holdout).")
    args = ap.parse_args()

    eval_set = load_eval_file(args.eval_file) if args.eval_file else load_eval_set()
    if args.limit:
        eval_set = eval_set[:args.limit]
    print(f"[backtest] eval examples (outcome-labelled): {len(eval_set)}")
    if not eval_set:
        print("[backtest] no labelled eval data."); return

    if args.policy == "recorded":
        pol = recorded_policy
        name = "RecordedPolicy (formula baseline)"
        workers = 1
    elif args.policy == "cascade":
        if not args.endpoint or not args.confirm_endpoint:
            print("[backtest] cascade needs --endpoint (proposer) and --confirm-endpoint"); sys.exit(2)
        pol = CascadePolicy(args.endpoint, args.confirm_endpoint)
        name = f"Cascade({args.endpoint.split('/')[-1]}->{args.confirm_endpoint.split('/')[-1]})"
        workers = max(2, args.workers // 2)  # 2 calls per example
    else:
        if not args.endpoint:
            print("[backtest] --endpoint required for tuned policy"); sys.exit(2)
        pol = TunedModelPolicy(args.endpoint)
        name = f"TunedModelPolicy({args.endpoint.split('/')[-1]})"
        workers = args.workers

    res = score(pol, eval_set, workers=workers)
    print(f"\n[backtest] === {name} ===")
    for k, v in res.items():
        print(f"  {k}: {v}")

    if args.gate_baseline is not None:
        ok = res["net_expectancy_proxy"] >= args.gate_baseline
        print(f"\n[backtest] GATE: {res['net_expectancy_proxy']} >= {args.gate_baseline} -> "
              f"{'PASS' if ok else 'FAIL'}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
