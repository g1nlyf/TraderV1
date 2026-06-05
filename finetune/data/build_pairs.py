"""
Build script for real_pairs.json — adds entry_type, stale, borderline, and
additional bad_wallet entries.
"""
import json
import copy
import itertools
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INPUT = "finetune/data/real_pairs_original.json"
OUTPUT = "finetune/data/real_pairs.json"

BAD_PNL_WALLET = "GxDC9e7SP9mzhDo4re5HbpLa2RW7gB9DtmThx4i4pXSq"

pairs = json.loads(open(INPUT, encoding="utf-8").read())

# ── Step 1: add entry_type + fix GxDC potential_signal → bad_wallet ──────────
def classify(p):
    # GxDC wallet always maps to bad_wallet regardless of original scenario
    if p["wallet"] == BAD_PNL_WALLET:
        return "bad_wallet"
    if p["scenario"] == "potential_signal":
        return "fresh"
    if p["scenario"] == "bad_wallet":
        return "bad_wallet"
    if p["scenario"] == "bad_token":
        return "bad_token"
    return "unknown"


new_pairs = []
for p in pairs:
    np = dict(p)
    # Force ALL GxDC entries to bad_wallet scenario so the E2E constraint holds
    if p["wallet"] == BAD_PNL_WALLET:
        np["scenario"] = "bad_wallet"
    np["entry_type"] = classify(p)
    new_pairs.append(np)

# ── Step 2: 20 stale entries from top-20 fresh by approx_liq ─────────────────
fresh = [p for p in new_pairs if p["entry_type"] == "fresh"]
fresh_sorted = sorted(fresh, key=lambda x: x["approx_liq"], reverse=True)
top20_fresh = fresh_sorted[:20]

stale_entries = []
for p in top20_fresh:
    s = dict(p)
    s["entry_type"] = "stale"
    s["signal_age_override_hours"] = 3.5
    stale_entries.append(s)

# ── Step 3: 10 borderline entries ─────────────────────────────────────────────
GOOD_WALLETS = [
    "2MFoS3MPtvyQ4Wh4M9pdfPjz6UhVoNbFbGJAskCPCj3h",
    "44zas59yMsNv3nwsjtf9zPCxvaxyvuhLPx6x4ERKXPti",
    "6TYDxGmVxkBPBmEfnmLXx6jVff9LknsjRHqdTjVyZmG8",
    "ARu4n5mFdZogZAravu7CcizaojWnS6oqka37gdLT5SZn",
    "HxjwdF326ZunmUwC1iXhfgL3ku78YsksN6n7Rfxzwr6b",
]

# Collect unique tokens with 15000 <= approx_liq <= 24000 from original file
seen = set()
borderline_tokens = []
for p in pairs:
    if 15000 <= p["approx_liq"] <= 24000 and p["token_mint"] not in seen:
        borderline_tokens.append(
            {"token_mint": p["token_mint"], "symbol": p["symbol"], "approx_liq": p["approx_liq"]}
        )
        seen.add(p["token_mint"])

# We need exactly 10; cycle tokens if fewer than 10 unique ones
wallet_cycle = itertools.cycle(GOOD_WALLETS)
token_cycle = itertools.cycle(borderline_tokens)

borderline_entries = []
for _ in range(10):
    wallet = next(wallet_cycle)
    tok = next(token_cycle)
    borderline_entries.append(
        {
            "wallet": wallet,
            "token_mint": tok["token_mint"],
            "symbol": tok["symbol"],
            "approx_liq": tok["approx_liq"],
            "scenario": "borderline",
            "entry_type": "borderline",
        }
    )

# ── Step 4a: 10 bad_wallet entries using GxDC wallet + good tokens ────────────
GOOD_TOKENS_FOR_BAD = [
    {"token_mint": "GbuHq6UTNUp8CaFsoPgUhxpPBnkVXGepDHgFhN2kpump", "symbol": "Yae", "approx_liq": 126757.82},
    {"token_mint": "4aeBSAusGHEEzBEG9DBYtTjvcQjTJWsNfNvfNioYpump", "symbol": "hentai", "approx_liq": 56190.37},
    {"token_mint": "7qkvtgs6QvpNnxDhZArZg29DcWGTVp5EFNJ1AtySpump", "symbol": "SELLUR", "approx_liq": 56631.03},
    {"token_mint": "9LooeuSKG3H2mxj9yxWvoNibVLuxsE8qeobuHjZfpump", "symbol": "LUCY", "approx_liq": 32955.64},
    {"token_mint": "BnK8QgRW6BGPbPV2b1tAZgxVwAJvJpEC9xPoQikRpump", "symbol": "Jim", "approx_liq": 25493.07},
    {"token_mint": "CMUJzTahkRDanjpPonDS87FQuyntSLWhUYRkR79EybSU", "symbol": "CELL", "approx_liq": 32795.97},
    {"token_mint": "D9gKwxJF9kFxFUki8KK2WxjqdLFBnnuvvVvmueCUpump", "symbol": "BOPO", "approx_liq": 37871.32},
    {"token_mint": "ESZLbp5qm8SPfiqAR2sDXrZNjo5hKZoD7FAFTmfCpump", "symbol": "DOZER", "approx_liq": 25013.25},
    {"token_mint": "BigGboBX6veMLQV6gzqgV9Pbx8LeobR6eDjUQicXpump", "symbol": "BAGELS", "approx_liq": 44192.3},
    {"token_mint": "PoPGUYiYjb79CR2Z5XwGpGkuL5G2gApYktbhAN4Tzhh", "symbol": "POP", "approx_liq": 29786.52},
]

gxdc_entries = []
for tok in GOOD_TOKENS_FOR_BAD:
    gxdc_entries.append(
        {
            "wallet": BAD_PNL_WALLET,
            "token_mint": tok["token_mint"],
            "symbol": tok["symbol"],
            "approx_liq": tok["approx_liq"],
            "scenario": "bad_wallet",
            "entry_type": "bad_wallet",
        }
    )

# ── Step 4b: 10 bad_wallet entries using other existing bad wallets ───────────
EXTRA_GOOD_TOKENS = [
    {"token_mint": "GbuHq6UTNUp8CaFsoPgUhxpPBnkVXGepDHgFhN2kpump", "symbol": "Yae", "approx_liq": 126757.82},
    {"token_mint": "7qkvtgs6QvpNnxDhZArZg29DcWGTVp5EFNJ1AtySpump", "symbol": "SELLUR", "approx_liq": 56631.03},
    {"token_mint": "4aeBSAusGHEEzBEG9DBYtTjvcQjTJWsNfNvfNioYpump", "symbol": "hentai", "approx_liq": 57234.18},
    {"token_mint": "D9gKwxJF9kFxFUki8KK2WxjqdLFBnnuvvVvmueCUpump", "symbol": "BOPO", "approx_liq": 37871.32},
    {"token_mint": "CMUJzTahkRDanjpPonDS87FQuyntSLWhUYRkR79EybSU", "symbol": "CELL", "approx_liq": 33094.66},
    {"token_mint": "BnK8QgRW6BGPbPV2b1tAZgxVwAJvJpEC9xPoQikRpump", "symbol": "Jim", "approx_liq": 37094.95},
    {"token_mint": "ESZLbp5qm8SPfiqAR2sDXrZNjo5hKZoD7FAFTmfCpump", "symbol": "DOZER", "approx_liq": 25013.25},
    {"token_mint": "9LooeuSKG3H2mxj9yxWvoNibVLuxsE8qeobuHjZfpump", "symbol": "LUCY", "approx_liq": 34901.29},
    {"token_mint": "BigGboBX6veMLQV6gzqgV9Pbx8LeobR6eDjUQicXpump", "symbol": "BAGELS", "approx_liq": 44192.3},
    {"token_mint": "PoPGUYiYjb79CR2Z5XwGpGkuL5G2gApYktbhAN4Tzhh", "symbol": "POP", "approx_liq": 29786.52},
]

# Collect unique bad wallets that are NOT GxDC
existing_bad_wallets = []
seen_wallets = set()
for p in pairs:
    if p["scenario"] == "bad_wallet" and p["wallet"] != BAD_PNL_WALLET:
        if p["wallet"] not in seen_wallets:
            existing_bad_wallets.append(p["wallet"])
            seen_wallets.add(p["wallet"])

extra_bad_entries = []
for i, wallet in enumerate(existing_bad_wallets[:10]):
    tok = EXTRA_GOOD_TOKENS[i % len(EXTRA_GOOD_TOKENS)]
    extra_bad_entries.append(
        {
            "wallet": wallet,
            "token_mint": tok["token_mint"],
            "symbol": tok["symbol"],
            "approx_liq": tok["approx_liq"],
            "scenario": "bad_wallet",
            "entry_type": "bad_wallet",
        }
    )

# ── Assemble ──────────────────────────────────────────────────────────────────
final_pairs = new_pairs + stale_entries + borderline_entries + gxdc_entries + extra_bad_entries

from collections import Counter
et = Counter(p["entry_type"] for p in final_pairs)
sc = Counter(p["scenario"] for p in final_pairs)
stale = [p for p in final_pairs if p.get("signal_age_override_hours")]
print(f"Total: {len(final_pairs)}")
print("entry_types:", dict(et))
print("scenarios:", dict(sc))
print(f"Stale: {len(stale)}")

# Write out
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(final_pairs, f, indent=2, ensure_ascii=False)
print(f"Written to {OUTPUT}")
