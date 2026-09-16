"""Re-runnable ALGOPACK access check. Never prints the API key.

Usage:  python tools/probe_algopack.py [YYYY-MM-DD]
Checks: auth, each dataset endpoint, history depth, pagination, freshness, rate behaviour.
"""
import re
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import certifi
import requests

ROOT = Path(__file__).resolve().parents[1]
APIM = "https://apim.moex.com/iss"
CA_URLS = ["https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer",
           "https://gu-st.ru/content/Other/doc/russian_trusted_sub_ca.cer"]
D = sys.argv[1] if len(sys.argv) > 1 else "2025-09-10"
TODAY = date.today().isoformat()


def load_key() -> str:
    m = re.search(r"^ALGOPACK_API_KEY=(.*)$", (ROOT / ".env").read_text(encoding="utf-8-sig"), re.M)
    return m.group(1).strip().strip('"').strip("'") if m else ""


def ca_bundle() -> str:
    """certifi + Russian Trusted Root/Sub CA (apim.moex.com cert chain).
    Uses repo copy certs/russian_trusted_ca.pem; downloads only if it is missing (gu-st.ru is flaky)."""
    import ssl
    local = ROOT / "certs" / "russian_trusted_ca.pem"
    if local.exists():
        extra = local.read_text()
    else:
        pems = []
        for url in CA_URLS:
            b = requests.get(url, timeout=60).content
            pems.append(b.decode().replace("\r", "") if b.startswith(b"-----BEGIN") else ssl.DER_cert_to_PEM_cert(b))
        extra = "\n".join(pems)
    path = Path(tempfile.gettempdir()) / "moex_ca_bundle.pem"
    path.write_text(Path(certifi.where()).read_text() + "\n" + extra, newline="\n")
    return str(path)


S = requests.Session()
S.verify = ca_bundle()
S.headers["Authorization"] = f"Bearer {load_key()}"


def probe(label, path, params=None, block="data"):
    t = time.time()
    try:
        r = S.get(f"{APIM}/{path}.json", params=params or {}, timeout=90)
    except Exception as e:
        print(f"[{label}] EXC {type(e).__name__}: {e}")
        return None
    ct = r.headers.get("content-type", "").split(";")[0]
    extra = {k: v for k, v in r.headers.items() if "limit" in k.lower() or "retry" in k.lower()}
    if r.status_code == 200 and ct == "text/html" and b"available only to" in r.content:
        print(f"[{label}] NO SUBSCRIPTION (HTML 'available only to subscribers')")
        return None
    if r.status_code != 200 or ct != "application/json":
        print(f"[{label}] {r.status_code} {ct} {r.text[:120]!r}")
        return None
    d = r.json()
    b = d.get(block, {})
    rows = b.get("data", [])
    if "ERROR_MESSAGE" in b.get("columns", []):
        print(f"[{label}] API ERROR: {rows}")
        return None
    cursors = {k: v for k, v in d.items() if "cursor" in k}
    print(f"[{label}] 200 {time.time() - t:.1f}s rows={len(rows)} blocks={list(d)} {extra or ''}")
    if rows:
        print("   columns:", b["columns"])
        print("   first:", rows[0][:6], "| last:", rows[-1][:6])
    if cursors:
        print("   cursor:", cursors)
    return d


print(f"== datasets, date {D} ==")
for m, t in [("eq", "sber"), ("fo", "si"), ("fx", "cnyrub_tom")]:
    for ds in ["tradestats", "orderstats", "obstats"]:
        if (m, ds) == ("fo", "orderstats"):
            continue
        probe(f"{m}/{ds}/{t}", f"datashop/algopack/{m}/{ds}/{t}", {"from": D, "till": D})
    probe(f"{m}/tradestats ALL", f"datashop/algopack/{m}/tradestats", {"date": D})
    probe(f"{m}/hi2/{t}", f"datashop/algopack/{m}/hi2/{t}", {"from": D, "till": D})
probe("eq/alerts ALL", "datashop/algopack/eq/alerts", {"date": D})
probe("futoi si", "analyticalproducts/futoi/securities/si", {"from": D, "till": D}, block="futoi")
probe("futoi si today (free plan: 14-day embargo)", "analyticalproducts/futoi/securities/si",
      {"from": TODAY, "till": TODAY}, block="futoi")
for label, p in [("SBER", "engines/stock/markets/shares/boards/TQBR/securities/SBER/candles"),
                 ("IMOEX", "engines/stock/markets/index/boards/SNDX/securities/IMOEX/candles"),
                 ("CNYRUB_TOM", "engines/currency/markets/selt/boards/CETS/securities/CNYRUB_TOM/candles")]:
    probe(f"candles {label} 1m", p, {"from": D, "till": D, "interval": 1}, block="candles")

print("\n== history depth ==")
for d_ in ["2019-06-03", "2020-01-06", "2023-01-10"]:
    probe(f"tradestats sber {d_}", "datashop/algopack/eq/tradestats/sber", {"from": d_, "till": d_})
probe("alerts ALL 2024-02-01", "datashop/algopack/eq/alerts", {"date": "2024-02-01"})

print("\n== pagination ==")
probe("tradestats sber 1 month", "datashop/algopack/eq/tradestats/sber", {"from": "2025-08-01", "till": "2025-08-31"})
probe("tradestats sber 1 month start=1000", "datashop/algopack/eq/tradestats/sber",
      {"from": "2025-08-01", "till": "2025-08-31", "start": 1000})
probe("eq/tradestats ALL start=1000", "datashop/algopack/eq/tradestats", {"date": D, "start": 1000})

print(f"\n== freshness (today {TODAY}, local {time.strftime('%H:%M:%S')}) ==")
probe("tradestats sber latest", "datashop/algopack/eq/tradestats/sber", {"from": TODAY, "till": TODAY, "latest": 1})
probe("candles SBER 1m today", "engines/stock/markets/shares/boards/TQBR/securities/SBER/candles",
      {"from": TODAY, "till": TODAY, "interval": 1}, block="candles")

print("\n== rate: 30 rapid requests ==")
codes, t = [], time.time()
for _ in range(30):
    codes.append(S.get(f"{APIM}/datashop/algopack/eq/tradestats/sber.json", params={"from": D, "till": D}, timeout=60).status_code)
print("   codes:", codes, f"{time.time() - t:.1f}s")
