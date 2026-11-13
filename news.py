"""
news.py — information feeds: headlines, narratives, trending coins, new tokens.

WHY THIS EXISTS, AND WHAT IT DELIBERATELY IS NOT
------------------------------------------------
There is a real edge in being informed early. Narratives rotate, sectors heat up,
and people who read widely notice before the crowd. That part is legitimate and
this module supports it.

What it is NOT is a "find the next 100x memecoin before it launches" tool.
That race is run by bots in the same block as the launch. A human refreshing a
feed is not early — they are exit liquidity. So every new-token feed here ships
with the objective survival numbers attached, because the base rate is the most
important fact about a brand-new token and it's the one nobody shows you.

Every source is free and needs no API key. Sources that fail are reported rather
than silently dropped, so you always know what you're not seeing.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

UA = "Mozilla/5.0 (compatible; QuantLab/1.0; personal research tool)"
_CACHE: dict[str, tuple[float, object]] = {}


# ----------------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------------

FEEDS = [
    # (key, display name, url, category)
    ("coindesk", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "news"),
    ("cointelegraph", "Cointelegraph", "https://cointelegraph.com/rss", "news"),
    ("decrypt", "Decrypt", "https://decrypt.co/feed", "news"),
    ("cryptoslate", "CryptoSlate", "https://cryptoslate.com/feed/", "news"),
    ("bitcoinmag", "Bitcoin Magazine", "https://bitcoinmagazine.com/feed", "news"),
    ("theblock", "The Block", "https://www.theblock.co/rss.xml", "news"),
    ("r_crypto", "r/CryptoCurrency", "https://www.reddit.com/r/CryptoCurrency/hot/.rss", "social"),
    ("r_solana", "r/solana", "https://www.reddit.com/r/solana/hot/.rss", "social"),
    ("r_cryptomoon", "r/CryptoMoonShots", "https://www.reddit.com/r/CryptoMoonShots/hot/.rss", "social"),
    ("gnews_crypto", "Google News: crypto",
     "https://news.google.com/rss/search?q=cryptocurrency+when:2d&hl=en-US&gl=US&ceid=US:en", "news"),
    ("gnews_solana", "Google News: Solana",
     "https://news.google.com/rss/search?q=solana+OR+pump.fun+when:2d&hl=en-US&gl=US&ceid=US:en", "news"),
]

# NOTE ON TWITTER/X: there is no free programmatic access any more. The API is
# paid, and the public mirrors (nitter instances) are almost all dead or rate
# limited. Rather than ship something that breaks silently, this module uses
# Google News (which indexes crypto media fast) and Reddit as the free
# substitutes. If you want X specifically, read it in a browser — no tool here
# can give you it legitimately without a paid key.


# ----------------------------------------------------------------------------
# Fetch helpers
# ----------------------------------------------------------------------------

def _get(url: str, timeout: int = 12) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/xml, application/json, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get_json(url: str, timeout: int = 12):
    return json.loads(_get(url, timeout).decode("utf-8", "replace"))


def _cached(key: str, ttl: int, fn):
    """Simple TTL cache. Feeds don't change second to second and rate limits are real."""
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


# ----------------------------------------------------------------------------
# RSS / Atom parsing  (stdlib only — no feedparser dependency)
# ----------------------------------------------------------------------------

_TAG = re.compile(r"\{.*?\}")          # strip XML namespaces
_HTML = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

_DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f%z",
    "%a, %d %b %Y %H:%M %z", "%d %b %Y %H:%M:%S %z",
]


def _clean_text(s: str | None) -> str:
    if not s:
        return ""
    return _WS.sub(" ", _HTML.sub(" ", s)).strip()


def _parse_date(s: str | None) -> int:
    if not s:
        return 0
    s = s.strip().replace("GMT", "+0000").replace("UTC", "+0000")
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    return 0


def parse_feed(xml_bytes: bytes, source: str, source_name: str, category: str) -> list[dict]:
    """Handle both RSS 2.0 (<item>) and Atom (<entry>) in one pass."""
    root = ET.fromstring(xml_bytes)
    items = []

    def tag(el):
        return _TAG.sub("", el.tag).lower()

    for el in root.iter():
        if tag(el) not in ("item", "entry"):
            continue
        rec = {"title": "", "link": "", "summary": "", "published": 0}
        for child in el:
            t = tag(child)
            if t == "title":
                rec["title"] = _clean_text(child.text)
            elif t == "link":
                rec["link"] = (child.get("href") or child.text or "").strip()
            elif t in ("description", "summary", "content"):
                if not rec["summary"]:
                    rec["summary"] = _clean_text(child.text)[:320]
            elif t in ("pubdate", "published", "updated", "date"):
                if not rec["published"]:
                    rec["published"] = _parse_date(child.text)
        if rec["title"]:
            rec.update({"source": source, "source_name": source_name, "category": category})
            items.append(rec)
    return items


def fetch_news(sources: list[str] | None = None, hours: int = 48,
               ttl: int = 300) -> dict:
    """Pull every feed, dedupe by title, newest first."""
    if os.environ.get("QUANTLAB_DEMO") == "1":
        return _demo_news()

    wanted = [f for f in FEEDS if not sources or f[0] in sources]

    def work():
        out, failed = [], []
        for key, name, url, cat in wanted:
            try:
                out.extend(parse_feed(_get(url), key, name, cat))
            except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError,
                    ValueError, TimeoutError, OSError) as e:
                failed.append({"source": name, "error": f"{type(e).__name__}"})
        return out, failed

    items, failed = _cached(f"news:{','.join(s[0] for s in wanted)}", ttl, work)

    cutoff = time.time() - hours * 3600
    seen, deduped = set(), []
    for it in sorted(items, key=lambda x: -x["published"]):
        norm = re.sub(r"[^a-z0-9]", "", it["title"].lower())[:70]
        if norm in seen:
            continue
        seen.add(norm)
        if it["published"] and it["published"] < cutoff:
            continue
        deduped.append(it)

    return {"items": deduped[:180], "failed": failed,
            "sources": [{"key": k, "name": n, "category": c} for k, n, _, c in FEEDS]}


# ----------------------------------------------------------------------------
# Narrative tracker — what is actually being talked about
# ----------------------------------------------------------------------------

# Words that show up constantly and tell you nothing.
_STOP = set("""the a an and or but for with from into over under this that these those what
when where why how who will would could should can may might must have has had been being was
were are is am do does did not no yes new now today s t re ve ll m d you your my his her its
their our all any some more most other than then there here about after before between during
as at by if in of on to up out off just like get got go going make made say says said
crypto cryptocurrency bitcoin price market markets coin coins token tokens news update updates
report reports says analyst analysts week month year day daily could may might reaches hits
top best worst big biggest huge major latest breaking""".split())

_TICKER_HINT = re.compile(r"\b([A-Z]{2,6})\b")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9.\-]{2,}")


def narratives(items: list[dict], top: int = 25) -> list[dict]:
    """
    Count what's being mentioned across all headlines in the window.

    This is the closest thing here to a real information edge: when a name you
    don't recognise suddenly appears across many outlets in 24 hours, something
    is happening. It won't be first — but it will be earlier than price.
    """
    counts: dict[str, dict] = {}
    now = time.time()

    for it in items:
        text = f"{it['title']} {it.get('summary','')}"
        age_h = max(0.0, (now - it["published"]) / 3600.0) if it["published"] else 24.0
        # Recent mentions count for more; a 48h-old headline is half a fresh one.
        weight = 1.0 / (1.0 + age_h / 24.0)

        words = set()
        for m in _WORD.finditer(text):
            w = m.group(0).strip(".-")
            lw = w.lower()
            if len(lw) < 3 or lw in _STOP or lw.isdigit():
                continue
            # Keep proper nouns and tickers; drop ordinary lowercase prose.
            if w[0].isupper() or w.isupper():
                words.add(w if w.isupper() else w.capitalize())

        for w in words:
            c = counts.setdefault(w, {"term": w, "mentions": 0, "score": 0.0,
                                      "sources": set(), "headlines": []})
            c["mentions"] += 1
            c["score"] += weight
            c["sources"].add(it["source_name"])
            if len(c["headlines"]) < 3:
                c["headlines"].append({"title": it["title"], "link": it["link"],
                                       "source": it["source_name"]})

    rows = []
    for c in counts.values():
        if c["mentions"] < 2:
            continue
        rows.append({**c, "sources": sorted(c["sources"]),
                     "source_count": len(c["sources"]),
                     "score": round(c["score"], 2)})
    # Mentioned by many DIFFERENT outlets matters more than repeated by one.
    rows.sort(key=lambda r: (-r["source_count"], -r["score"]))
    return rows[:top]


# ----------------------------------------------------------------------------
# Trending coins (CoinGecko, free, keyless)
# ----------------------------------------------------------------------------

def fetch_trending(ttl: int = 300) -> dict:
    if os.environ.get("QUANTLAB_DEMO") == "1":
        return _demo_trending()

    def work():
        d = _get_json("https://api.coingecko.com/api/v3/search/trending")
        rows = []
        for c in d.get("coins", [])[:15]:
            i = c.get("item", {})
            data = i.get("data", {}) or {}
            rows.append({
                "name": i.get("name"), "symbol": (i.get("symbol") or "").upper(),
                "rank": i.get("market_cap_rank"),
                "price_usd": data.get("price"),
                "change_24h": (data.get("price_change_percentage_24h") or {}).get("usd"),
                "market_cap": data.get("market_cap"),
                "volume": data.get("total_volume"),
                "id": i.get("id"),
            })
        return {"coins": rows, "note": "CoinGecko's most-searched coins in the last 24h."}
    try:
        return _cached("trending", ttl, work)
    except Exception as e:
        return {"coins": [], "error": f"{type(e).__name__}: {e}"}


# ----------------------------------------------------------------------------
# New tokens — with the base rates attached
# ----------------------------------------------------------------------------

# Sourced figures, shown in the UI next to every new-token feed.
BASE_RATES = {
    "headline": "What actually happens to brand-new tokens",
    "facts": [
        "98.6% of over 7 million Pump.fun tokens studied by Solidus Labs fell below $1,000 in liquidity — effectively worthless.",
        "Roughly 1% of tokens launched each day ever 'graduate' to a real DEX pool with locked liquidity. About 99% die first.",
        "In April 2026 — one of the platform's better months — 96% of wallets either lost money or made under $500.",
        "The launch window is contested by bots operating in the same block. A human reading a feed is not early.",
    ],
    "sources": [
        {"label": "Solidus Labs / Pump.fun 98.6% figure", "url": "https://www.mexc.com/news/410195"},
        {"label": "Graduation rate data", "url": "https://www.cryptopolitan.com/pump-fun-token-graduations-six-month-high/"},
        {"label": "Wallet profitability study", "url": "https://www.crowdfundinsider.com/2026/05/277755-solana-based-meme-coins-trading-platform-pump-fun-makes-recovery-research/"},
        {"label": "Rug pull statistics", "url": "https://deepstrike.io/blog/rug-pull-statistics"},
    ],
}


def _risk_flags(pool: dict) -> tuple[int, list[str]]:
    """
    Objective, mechanical risk assessment of a new pool.

    Deliberately not a "gem score". Every check here is a way you can lose
    everything, expressed as a fact about the pool rather than an opinion.
    """
    flags, risk = [], 0
    liq = pool.get("liquidity_usd") or 0
    vol = pool.get("volume_24h") or 0
    age_h = pool.get("age_hours")
    buys, sells = pool.get("buys_24h") or 0, pool.get("sells_24h") or 0

    if liq < 10_000:
        risk += 3
        flags.append(f"Liquidity is only ${liq:,.0f} — you may not be able to sell at any price.")
    elif liq < 50_000:
        risk += 2
        flags.append(f"Thin liquidity (${liq:,.0f}). A moderate sell order moves the price hard.")

    if age_h is not None and age_h < 1:
        risk += 3
        flags.append(f"Under {age_h * 60:.0f} minutes old. No track record whatsoever.")
    elif age_h is not None and age_h < 24:
        risk += 1
        flags.append(f"Only {age_h:.0f} hours old.")

    if liq > 0 and vol > liq * 10:
        risk += 2
        flags.append(f"24h volume is {vol / liq:.0f}× the liquidity — a pattern consistent with wash trading.")

    total = buys + sells
    if total > 30 and sells > 0 and buys / max(sells, 1) > 4:
        risk += 1
        flags.append(f"{buys} buys vs {sells} sells — heavily one-sided, which reverses fast.")

    chg = pool.get("change_24h")
    if chg is not None and chg > 300:
        risk += 2
        flags.append(f"Up {chg:,.0f}% in 24h. You would be buying from whoever is about to sell.")

    return risk, flags


def fetch_new_pools(network: str = "solana", ttl: int = 120) -> dict:
    """
    Newly created liquidity pools, via GeckoTerminal's free API.

    Presented with liquidity, age and volume so the numbers speak. This is the
    honest version of a "new coin alert": here is what exists, here is how
    fragile it is, here is the base rate for the category.
    """
    if os.environ.get("QUANTLAB_DEMO") == "1":
        return _demo_pools(network)

    def work():
        url = (f"https://api.geckoterminal.com/api/v2/networks/{network}/new_pools"
               f"?page=1")
        d = _get_json(url)
        now = time.time()
        rows = []
        for p in d.get("data", [])[:40]:
            a = p.get("attributes", {}) or {}
            created = _parse_date(a.get("pool_created_at"))
            age_h = ((now - created) / 3600.0) if created else None
            tx = (a.get("transactions", {}) or {}).get("h24", {}) or {}
            row = {
                "name": a.get("name"),
                "address": a.get("address"),
                "price_usd": _f(a.get("base_token_price_usd")),
                "liquidity_usd": _f(a.get("reserve_in_usd")),
                "volume_24h": _f((a.get("volume_usd", {}) or {}).get("h24")),
                "change_24h": _f((a.get("price_change_percentage", {}) or {}).get("h24")),
                "change_1h": _f((a.get("price_change_percentage", {}) or {}).get("h1")),
                "age_hours": age_h,
                "created_at": created,
                "buys_24h": tx.get("buys"), "sells_24h": tx.get("sells"),
                "url": f"https://www.geckoterminal.com/{network}/pools/{a.get('address')}",
            }
            row["risk_score"], row["risk_flags"] = _risk_flags(row)
            rows.append(row)
        rows.sort(key=lambda r: -(r["created_at"] or 0))
        return {"network": network, "pools": rows, "base_rates": BASE_RATES}

    try:
        return _cached(f"pools:{network}", ttl, work)
    except Exception as e:
        return {"network": network, "pools": [], "base_rates": BASE_RATES,
                "error": f"{type(e).__name__}: {e}"}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------
# Offline fixtures so the UI and tests work with no network
# ----------------------------------------------------------------------------

def _demo_news() -> dict:
    now = int(time.time())
    seed = [
        ("Solana network activity hits new high as DEX volume climbs", "CoinDesk", "news", 1),
        ("Ethereum staking withdrawals slow ahead of upgrade", "Cointelegraph", "news", 3),
        ("Pump.fun revenue rebounds but token launches stay flat", "Decrypt", "news", 5),
        ("Bitcoin ETF inflows turn positive after three-week drought", "CoinDesk", "news", 7),
        ("Solana DePIN projects draw institutional attention", "The Block", "news", 9),
        ("Discussion: what did you learn from your worst trade?", "r/CryptoCurrency", "social", 2),
        ("Layer 2 fees drop sharply following blob capacity increase", "CryptoSlate", "news", 12),
        ("Analysts debate whether Solana can hold its DEX market share", "Google News: Solana", "news", 14),
    ]
    items = [{
        # lowercase on purpose — the narrative counter only picks up proper
        # nouns, and a capitalised fixture word would rank above real terms
        "title": t, "link": "https://example.invalid/demo",
        "summary": "placeholder text used when running offline.",
        "published": now - h * 3600, "source": s.lower().replace(" ", "_"),
        "source_name": s, "category": c,
    } for t, s, c, h in seed]
    return {"items": items, "failed": [], "demo": True,
            "sources": [{"key": k, "name": n, "category": c} for k, n, _, c in FEEDS]}


def _demo_trending() -> dict:
    return {"coins": [
        {"name": "Solana", "symbol": "SOL", "rank": 5, "price_usd": 148.2,
         "change_24h": 4.1, "market_cap": "$70B", "volume": "$3.1B", "id": "solana"},
        {"name": "Jupiter", "symbol": "JUP", "rank": 62, "price_usd": 0.81,
         "change_24h": -2.3, "market_cap": "$1.1B", "volume": "$180M", "id": "jupiter"},
    ], "note": "Demo fixture.", "demo": True}


def _demo_pools(network: str) -> dict:
    now = time.time()
    raw = [
        {"name": "DEMOCAT / SOL", "price_usd": 0.000031, "liquidity_usd": 4200,
         "volume_24h": 91000, "change_24h": 640.0, "change_1h": -18.0,
         "age_hours": 0.4, "buys_24h": 812, "sells_24h": 140},
        {"name": "TESTDOG / SOL", "price_usd": 0.00092, "liquidity_usd": 38000,
         "volume_24h": 120000, "change_24h": 45.0, "change_1h": 3.2,
         "age_hours": 6.0, "buys_24h": 340, "sells_24h": 290},
        {"name": "SAMPLE / SOL", "price_usd": 0.014, "liquidity_usd": 210000,
         "volume_24h": 480000, "change_24h": 12.0, "change_1h": 1.1,
         "age_hours": 40.0, "buys_24h": 900, "sells_24h": 870},
    ]
    pools = []
    for r in raw:
        r["created_at"] = int(now - r["age_hours"] * 3600)
        r["address"] = "demo"
        r["url"] = "https://example.invalid/demo"
        r["risk_score"], r["risk_flags"] = _risk_flags(r)
        pools.append(r)
    return {"network": network, "pools": pools, "base_rates": BASE_RATES, "demo": True}
