"""
Text-to-text Signal Reviewer — inference path for the outcome-trained models (v2/v3).

The tuned flash models are text-to-text (Vertex SFT rejects function-call format),
so the agentic tool-loop reviewer cannot drive them. This adapter implements the
blueprint architecture instead:

  S1 (deterministic): fetch evidence (wallet/token/market) via stage2-v2-tool
  L2 (model):         ONE text-to-text call → decision JSON
  optional cascade:   v3 proposes (recall) → v2 confirms (precision)

Faster and deterministic vs the agentic loop (no multi-turn tool latency).
Reads the champion endpoint from finetune/inference/champion.json (or .trained_model).

Usage:
    from finetune.inference.signal_reviewer_textmode import TextModeReviewer
    r = TextModeReviewer()                      # champion from champion.json
    decision = r.review(wallet, token_mint)     # {'decision_type','confidence','pre_action_reasoning'}

    # cascade:
    r = TextModeReviewer(cascade=True)
    decision = r.review(wallet, token_mint)     # signal only if v3 AND v2 agree
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WALLETSCARPER_ROOT = ROOT / "WalletScarper"
WALLETSCARPER_PYTHON = WALLETSCARPER_ROOT / ".venv" / "Scripts" / "python.exe"
PROMPTS_DIR = ROOT / "finetune" / "prompts"
CHAMPION_FILE = ROOT / "finetune" / "inference" / "champion.json"
TRAINED_MODEL_FILE = ROOT / "finetune" / "inference" / ".trained_model"

PROJECT = os.environ.get("VERTEX_PROJECT", "sft-test-clean")
LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")
SYSTEM_PROMPT = (PROMPTS_DIR / "teacher_system.md").read_text(encoding="utf-8")

TOOL_NAME_MAP = {
    "wallet_profile_history": "wallet.profile_history",
    "token_get_profile": "token.get_profile",
    "market_get_token_snapshot": "market.get_token_snapshot",
}
_STRIP_ENV = {"PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"}


def _clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}


def _call_tool(tool: str, payload: dict) -> dict:
    v2 = TOOL_NAME_MAP.get(tool, tool)
    if not WALLETSCARPER_PYTHON.exists():
        return {"ok": False, "error": f"venv missing: {WALLETSCARPER_PYTHON}"}
    try:
        r = subprocess.run(
            [str(WALLETSCARPER_PYTHON), "-m", "walletscarper", "stage2-v2-tool", v2,
             "--payload-json", json.dumps(payload)],
            cwd=str(WALLETSCARPER_ROOT), capture_output=True, text=True,
            timeout=60, check=False, env=_clean_env(),
        )
        if r.returncode != 0 and not r.stdout.strip():
            return {"ok": False, "error": f"rc={r.returncode}", "stderr": r.stderr[:200]}
        return json.loads(r.stdout.strip())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _resolve_champion() -> str:
    if CHAMPION_FILE.exists():
        try:
            return json.loads(CHAMPION_FILE.read_text(encoding="utf-8"))["endpoint"]
        except Exception:
            pass
    if TRAINED_MODEL_FILE.exists():
        m = TRAINED_MODEL_FILE.read_text(encoding="utf-8").strip()
        if m:
            return m
    return "gemini-2.5-flash"


def _candidates() -> dict:
    if CHAMPION_FILE.exists():
        try:
            return json.loads(CHAMPION_FILE.read_text(encoding="utf-8")).get("candidates", {})
        except Exception:
            return {}
    return {}


class TextModeReviewer:
    def __init__(self, endpoint: str | None = None, cascade: bool = False,
                 timeout_ms: int = 25000):
        from google import genai
        from google.genai import types
        self._types = types
        self.client = genai.Client(
            vertexai=True, project=PROJECT, location=LOCATION,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
        self.endpoint = endpoint or _resolve_champion()
        self.cascade = cascade
        cand = _candidates()
        self.v3 = cand.get("v3", self.endpoint)
        self.v2 = cand.get("v2")

    # ── evidence (S1) ────────────────────────────────────────────────────────────
    def fetch_evidence(self, wallet: str, token_mint: str) -> dict:
        return {
            "wallet": _call_tool("wallet_profile_history", {"wallet": wallet}),
            "token": _call_tool("token_get_profile", {"token_mint": token_mint}),
            "market": _call_tool("market_get_token_snapshot", {"token_mint": token_mint}),
        }

    def build_prompt(self, wallet: str, token_mint: str, ev: dict, observed_at: str = "") -> str:
        wp = ev["wallet"].get("profile", ev["wallet"])
        tp = ev["token"].get("profile", ev["token"])
        ms = ev["market"].get("snapshot", ev["market"])
        return "\n".join([
            "AUTONOMOUS SIGNAL REVIEW", "",
            "Signal event:",
            f"  wallet: {wallet}",
            f"  token_mint: {token_mint}",
            f"  side: buy",
            f"  observed_at: {observed_at}", "",
            "EVIDENCE:",
            "--- WALLET PROFILE ---", json.dumps(wp, ensure_ascii=False),
            "--- TOKEN PROFILE ---", json.dumps(tp, ensure_ascii=False),
            "--- MARKET SNAPSHOT ---", json.dumps(ms, ensure_ascii=False), "",
            "Review the evidence and output your decision as JSON "
            "with keys: decision_type, confidence, pre_action_reasoning.",
        ])

    # ── model call (L2) ──────────────────────────────────────────────────────────
    def _call_model(self, endpoint: str, prompt: str) -> dict:
        types = self._types
        try:
            resp = self.client.models.generate_content(
                model=endpoint,
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT, temperature=0.0, max_output_tokens=1024),
            )
            txt = (resp.text or "").strip()
            blob = txt[txt.find("{"): txt.rfind("}") + 1] if "{" in txt else ""
            try:
                return json.loads(blob)
            except Exception:
                dm = re.search(r'"decision_type"\s*:\s*"(\w+)"', txt)
                cm = re.search(r'"confidence"\s*:\s*"(\w+)"', txt)
                rm = re.search(r'"pre_action_reasoning"\s*:\s*"(.*?)"', txt, re.DOTALL)
                return {"decision_type": dm.group(1) if dm else "no_trade",
                        "confidence": cm.group(1) if cm else None,
                        "pre_action_reasoning": rm.group(1) if rm else txt[:300]}
        except Exception as e:
            return {"decision_type": "no_trade", "confidence": None,
                    "pre_action_reasoning": f"model error: {e}", "_error": str(e)[:80]}

    # ── public ───────────────────────────────────────────────────────────────────
    def review(self, wallet: str, token_mint: str, observed_at: str = "") -> dict:
        ev = self.fetch_evidence(wallet, token_mint)
        prompt = self.build_prompt(wallet, token_mint, ev, observed_at)

        if not self.cascade or not self.v2:
            return self._call_model(self.endpoint, prompt)

        # Cascade: v3 proposes (recall), v2 confirms (precision).
        proposal = self._call_model(self.v3, prompt)
        if proposal.get("decision_type") != "signal":
            return proposal
        confirm = self._call_model(self.v2, prompt)
        if confirm.get("decision_type") == "signal":
            proposal["cascade"] = "v3_signal+v2_confirm"
            return proposal
        return {"decision_type": "no_trade",
                "confidence": None,
                "pre_action_reasoning": "v3 proposed signal; v2 precision-gate overrode to no_trade.",
                "cascade": "v3_signal+v2_override"}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--wallet", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--cascade", action="store_true")
    a = ap.parse_args()
    r = TextModeReviewer(cascade=a.cascade)
    print(f"champion endpoint: {r.endpoint.split('/')[-1]}  cascade={a.cascade}")
    out = r.review(a.wallet, a.token)
    print(json.dumps(out, ensure_ascii=False, indent=2))
