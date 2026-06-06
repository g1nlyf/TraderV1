"""H-166 — deterministic, paper-only wallet-distribution RISK/EXIT/NO-TRADE overlay.

Converts the H-162/H-166 research result (coordinated quality-wallet selling precedes drops; exiting a held
long on a during-hold distribution cluster beats hold AND a shuffled-lag control 100% of draws) into a pure,
deterministic, point-in-time decision function that a Stage-2 risk service can call.

Design rules (binding):
  * DETERMINISTIC: pure function of (events, wallet_quality, as_of, config). No clock, no network, no DB,
    no randomness. Same inputs -> same verdict. (Stage-2 services own risk; Hermes only interprets context.)
  * POINT-IN-TIME: only events with ts < as_of are ever read. Future events are dropped defensively.
  * QUALITY = point-in-time only. `wallet_quality` must be realized skill computed from PRE-as_of trades
    (e.g. build_events.WalletSkill.at). If absent, the signal DEGRADES (confidence=low) and never hard-vetoes.
  * PAPER-ONLY: returns advice + evidence. Places no trades. Never sizes capital.
  * SOURCE PURITY: any event with source != "organic" taints the verdict -> evidence.source_purity="non_organic".

Verdicts:
  entry:    pass | watch | no_trade      (watch = bounce candidate per buy-after-absorbed-distribution finding)
  position: hold | exit_candidate
Thresholds calibrated to test_capturable.py (distribution_pre_t / distribution_in_hold) which produced the
+8.8% buy-after-distribution and the +3.9/+5.4% exit-overlay (perm 0.000, beats control 100%).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

SIGNAL_VERSION = "h166.v1"


@dataclass(frozen=True)
class Config:
    window_s: int = 900            # distribution lookback (matches research distribution_pre_t)
    recent_s: int = 300            # "active vs absorbed" sub-window
    k_sellers: int = 3             # min distinct sellers for a cluster
    k_quality_sellers: int = 1     # min distinct QUALITY sellers (point-in-time skill > quality_min)
    quality_min: float = 0.0       # realized SOL PnL > 0 = "quality" (point-in-time)
    sell_buy_ratio: float = 1.0    # sell_sol must exceed buy_sol * this
    quality_sell_frac: float = 0.40  # quality-seller SOL / total sell SOL to call it quality-led
    exit_recent_s: int = 600       # during-hold: cluster must be recent (since this lookback)


@dataclass
class Pressure:
    n_sellers: int = 0
    n_buyers: int = 0
    sell_sol: float = 0.0
    buy_sol: float = 0.0
    n_quality_sellers: int = 0
    quality_sell_sol: float = 0.0
    n_sellers_recent: int = 0
    n_quality_sellers_recent: int = 0
    window_s: int = 0

    @property
    def sell_buy_ratio(self) -> float:
        return self.sell_sol / self.buy_sol if self.buy_sol > 0 else (float("inf") if self.sell_sol > 0 else 0.0)

    @property
    def quality_sell_frac(self) -> float:
        return self.quality_sell_sol / self.sell_sol if self.sell_sol > 0 else 0.0


@dataclass
class Verdict:
    decision: str
    score: float                       # 0..1 distribution-pressure intensity
    confidence: str                    # high | low (low = no point-in-time quality supplied)
    reasons: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    def to_evidence_ref(self) -> dict:
        """Shape suitable for Stage-2 normalized_evidence_refs / risk_check metadata."""
        return {"signal": SIGNAL_VERSION, "decision": self.decision, "score": round(self.score, 4),
                "confidence": self.confidence, "reasons": self.reasons, **self.evidence}


def _pressure(events, as_of, wallet_quality, cfg: Config) -> tuple[Pressure, bool]:
    """Compute distribution pressure from events strictly BEFORE as_of. Returns (Pressure, organic)."""
    p = Pressure(window_s=cfg.window_s)
    lo = as_of - cfg.window_s
    rec = as_of - cfg.recent_s
    sellers, buyers, qsellers = set(), set(), set()
    sellers_rec, qsellers_rec = set(), set()
    organic = True
    for e in events:
        ts = e["ts"]
        if ts >= as_of or ts < lo:        # POINT-IN-TIME: drop future + out-of-window
            continue
        if e.get("source", "organic") != "organic":
            organic = False
        w, side, sol = e["wallet"], e["side"], float(e.get("sol", 0.0))
        is_q = (wallet_quality is not None) and (wallet_quality.get(w, 0.0) > cfg.quality_min)
        if side == "sell":
            sellers.add(w); p.sell_sol += sol
            if is_q:
                qsellers.add(w); p.quality_sell_sol += sol
            if ts >= rec:
                sellers_rec.add(w)
                if is_q:
                    qsellers_rec.add(w)
        elif side == "buy":
            buyers.add(w); p.buy_sol += sol
    p.n_sellers, p.n_buyers = len(sellers), len(buyers)
    p.n_quality_sellers = len(qsellers)
    p.n_sellers_recent, p.n_quality_sellers_recent = len(sellers_rec), len(qsellers_rec)
    return p, organic


def _score(p: Pressure, cfg: Config) -> float:
    """0..1 intensity: blends seller breadth, sell/buy dominance, quality leadership."""
    breadth = min(p.n_sellers / (cfg.k_sellers * 2), 1.0)
    dom = min((p.sell_buy_ratio - 1.0) / 2.0, 1.0) if p.sell_buy_ratio != float("inf") else 1.0
    dom = max(dom, 0.0)
    qual = min(p.quality_sell_frac / cfg.quality_sell_frac, 1.0) if cfg.quality_sell_frac > 0 else 0.0
    qlead = min(p.n_quality_sellers / max(cfg.k_quality_sellers, 1), 1.0)
    return round(0.30 * breadth + 0.25 * dom + 0.25 * qual + 0.20 * qlead, 4)


def _cluster(p: Pressure, cfg: Config, has_quality: bool = True) -> bool:
    base = p.n_sellers >= cfg.k_sellers and p.sell_sol > p.buy_sol * cfg.sell_buy_ratio
    if not has_quality:                       # DEGRADED: count-based only (will be downgraded to watch)
        return base
    return base and (p.n_quality_sellers >= cfg.k_quality_sellers or p.quality_sell_frac >= cfg.quality_sell_frac)


def evaluate_entry(token, as_of, events, wallet_quality=None, cfg: Config = Config()) -> Verdict:
    """Entry advice. ACTIVE quality distribution -> no_trade; ABSORBED (quiet recently) -> watch (bounce); else pass.

    Rationale: research shows buying AFTER absorbed distribution bounces (+8.8% vs fresh-FOMO), but buying INTO
    ongoing quality distribution continues down. So absorbed => watch (not immediate buy), active => no_trade.
    """
    p, organic = _pressure(events, as_of, wallet_quality, cfg)
    conf = "high" if wallet_quality is not None else "low"
    score = _score(p, cfg)
    ev = {"token": token, "as_of": as_of, "organic": organic, **asdict(p),
          "sell_buy_ratio": round(p.sell_buy_ratio, 3) if p.sell_buy_ratio != float("inf") else "inf",
          "quality_sell_frac": round(p.quality_sell_frac, 3)}
    reasons = []
    if not _cluster(p, cfg, has_quality=(conf == "high")):
        return _finalize(Verdict("pass", score, conf, ["no_distribution_cluster"], ev), organic, conf)
    active = p.n_quality_sellers_recent >= cfg.k_quality_sellers or p.n_sellers_recent >= cfg.k_sellers
    if active:
        reasons = ["active_quality_distribution", f"recent_quality_sellers={p.n_quality_sellers_recent}"]
        dec = "no_trade"
    else:
        reasons = ["absorbed_distribution_bounce_candidate", f"quality_sellers={p.n_quality_sellers}"]
        dec = "watch"
    # DEGRADATION: without point-in-time quality, never hard-veto -> downgrade no_trade to watch.
    if conf == "low" and dec == "no_trade":
        dec = "watch"; reasons.append("downgraded_no_quality_data")
    return _finalize(Verdict(dec, score, conf, reasons, ev), organic, conf)


def evaluate_position(token, as_of, entry_ts, events, wallet_quality=None, cfg: Config = Config()) -> Verdict:
    """Open-position advice. Recent during-hold quality distribution cluster -> exit_candidate; else hold."""
    # restrict window to since entry, but cap at exit_recent_s (recent cluster = actionable)
    eff_lo = max(entry_ts, as_of - cfg.exit_recent_s)
    sub = [e for e in events if eff_lo <= e["ts"] < as_of]
    cfg_recent = Config(window_s=as_of - eff_lo, recent_s=cfg.recent_s, k_sellers=cfg.k_sellers,
                        k_quality_sellers=cfg.k_quality_sellers, quality_min=cfg.quality_min,
                        sell_buy_ratio=cfg.sell_buy_ratio, quality_sell_frac=cfg.quality_sell_frac)
    p, organic = _pressure(sub, as_of, wallet_quality, cfg_recent)
    conf = "high" if wallet_quality is not None else "low"
    score = _score(p, cfg_recent)
    ev = {"token": token, "as_of": as_of, "entry_ts": entry_ts, "organic": organic, **asdict(p),
          "sell_buy_ratio": round(p.sell_buy_ratio, 3) if p.sell_buy_ratio != float("inf") else "inf",
          "quality_sell_frac": round(p.quality_sell_frac, 3)}
    if _cluster(p, cfg_recent, has_quality=(conf == "high")):
        rs = ["during_hold_quality_distribution", f"quality_sellers={p.n_quality_sellers}"]
        if conf == "low":
            rs.append("count_based_degraded")
        v = Verdict("exit_candidate", score, conf, rs, ev)
    else:
        v = Verdict("hold", score, conf, ["no_distribution_cluster"], ev)
    return _finalize(v, organic, conf)


def _finalize(v: Verdict, organic: bool, conf: str) -> Verdict:
    v.evidence["source_purity"] = "organic" if organic else "non_organic"
    if not organic:
        v.reasons.append("non_organic_source_present")
    v.evidence["signal_version"] = SIGNAL_VERSION
    v.evidence["confidence"] = conf
    return v
