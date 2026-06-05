import numpy as np, glob, os
from pathlib import Path
CACHE = Path(__file__).resolve().parents[2] / "finetune" / "data" / "funding_cache"
for suf in ["_binance", "_spot_8h", "_perp_8h"]:
    fs = sorted(glob.glob(str(CACHE / f"*USDT{suf}.npz")))
    z = np.load(fs[0])
    k = list(z.keys())
    print(suf, os.path.basename(fs[0]), "keys=", k, "len=", len(z[k[0]]))

def bases(suf):
    return set(os.path.basename(f)[:-len(f"USDT{suf}.npz")] for f in glob.glob(str(CACHE / f"*USDT{suf}.npz")))

spot = bases("_spot_8h"); perp = bases("_perp_8h"); binance = bases("_binance"); bybit = bases("_bybit")
print("n binance=", len(binance), "n bybit=", len(bybit), "n spot=", len(spot), "n perp=", len(perp))

# listing date per binance name = first funding ts; report sorted by listing date
rows = []
for b in sorted(binance):
    z = np.load(CACHE / f"{b}USDT_binance.npz")
    t = z["t"]; r = z["r"]
    if len(t) < 5:
        continue
    first = int(t.min()); last = int(t.max())
    span_d = (last - first) / (24 * 3600 * 1000)
    rows.append((first, b, len(t), span_d, b in spot, b in bybit))
rows.sort()  # earliest listing first
print(f"\n{'name':<12}{'listing_date':<22}{'n_obs':>6}{'span_d':>8}  spot  bybit")
import datetime as dt
for first, b, n, span, hs, hy in rows:
    d = dt.datetime.utcfromtimestamp(first/1000).strftime("%Y-%m-%d")
    print(f"{b:<12}{d:<22}{n:>6}{span:>8.0f}   {'Y' if hs else '.'}     {'Y' if hy else '.'}")

# how many "new listings" (span < 120 d, i.e. listed within window with short history)?
newish = [b for first, b, n, span, hs, hy in rows if span < 120]
print(f"\nNames with <120d history (candidate 'new listings'): {len(newish)} -> {newish}")
