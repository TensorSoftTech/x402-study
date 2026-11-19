#!/usr/bin/env python3
"""x402 open-book analysis: run after census_pull completes.
Produces CSVs for the study: funnel, price dist, niche quadrant, leaderboard join, github join."""
import json, csv, collections, os, re, urllib.request, gzip, statistics, datetime
D = os.path.expanduser("~/Documents/VAULT/Vault/RW/data/x402-open-book")
G = lambda f: os.path.join(D, f)

# ---------- load census ----------
items = {}
for l in open(G("bazaar_raw.jsonl")):
    try: d = json.loads(l)
    except Exception: continue
    rid = d.get("resource") or json.dumps(d)[:64]
    items[rid] = d
print("census unique resources:", len(items))

def acc(d):  # accepts[0] price/network
    a = (d.get("accepts") or [{}])[0]
    return (float(a.get("amount") or 0) / 1e6, a.get("network") or "?")
def q(d):
    return d.get("quality") or (d.get("metadata") or {}).get("quality") or {}
def svc(d):
    return (str(d.get("resource") or "") + " " + (d.get("description") or "")).lower()
def site(d):
    return d.get("resource") if isinstance(d.get("resource"), str) else (d.get("metadata") or {}).get("site") or "" 

NICHES = [("onchain-data", r"onchain|on-chain|blockchain data|wallet|address|txn|transaction|dex|defillama|token price|chain data"),
          ("web-scrape/browse", r"scrape|browse|reader|web content|screenshot|crawl|fetch url|web data"),
          ("llm-ai", r"\bllm\b|openai|gpt|claude|gemini|ai inference|completion|embedding|agent|model"),
          ("market-data", r"market data|price feed|ticker|quote|candle|orderbook|funding|prediction market"),
          ("news", r"news|headlin|rss|article"),
          ("search", r"search|serp|lookup"),
          ("weather", r"weather|forecast|temperature"),
          ("media/image", r"image|video|media|generat|sticker|logo"),
          ("finance/payments", r"payment|invoice|stripe|fiat|exchange rate|forex|compliance|kyc|sanction"),
          ("dev-tools", r"api test|dns|domain|ssl|deploy|hosting|sdk|developer"),]
def niche(d):
    t = svc(d)
    for n, rx in NICHES:
        if re.search(rx, t): return n
    return "other"

bitrefill = sum(1 for d in items.values() if "bitrefill" in json.dumps(d).lower())

# ---------- funnel ----------
rows = []
for rid, d in items.items():
    price, net = acc(d); qq = q(d)
    calls = int(qq.get("l30DaysTotalCalls") or 0); payers = int(qq.get("l30DaysUniquePayers") or 0)
    rows.append({"id": rid, "niche": niche(d), "price": price, "net": net, "calls30": calls, "payers30": payers,
                 "site": site(d)[:80], "svc": (svc(d)[:40])})
with open(G("data/resources.csv"), "w") as o:
    w = csv.DictWriter(o, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
n = len(rows)
called = sum(1 for r in rows if r["calls30"] > 0)
paid = sum(1 for r in rows if r["payers30"] > 0)
repeat = sum(1 for r in rows if r["payers30"] >= 2)
print(f"FUNNEL listed={n:,} called30={called:,} ({100*called/n:.1f}%) paid30={paid:,} ({100*paid/n:.1f}%) repeaters>=2={repeat:,}")
with open(G("data/funnel.csv"), "w") as o:
    o.write("stage,n,pct\n")
    o.write(f"listed,{n},100\ncalled in 30d,{called},{100*called/n:.2f}\nany payer,{paid},{100*paid/n:.2f}\nrepeat payers,{repeat},{100*repeat/n:.2f}\nbitrefill-goods rails,{bitrefill}\n")

# ---------- niche quadrant ----------
agg = collections.defaultdict(lambda: [0, 0, 0, 0.0])
for r in rows:
    a = agg[r["niche"]]; a[0] += 1; a[1] += 1 if r["calls30"] else 0; a[2] += 1 if r["payers30"] else 0
    a[3] += r["payers30"] * r["price"]  # crude demand proxy
with open(G("data/niches.csv"), "w") as o:
    w = csv.writer(o); w.writerow(["niche", "listed", "called30", "paid30", "demandproxy_usd"])
    for k, v in sorted(agg.items(), key=lambda x: -x[1][0]): w.writerow([k] + v)

# ---------- leaderboard join ----------
try:
    lb = json.load(open(G("leaderboard.json")))
    sellers = (lb.get("sellers") or lb.get("rows") or lb.get("leaderboard") or []) if isinstance(lb, dict) else lb
    domains = set()
    for s in sellers:
        us = s.get("origins") or [s.get("domain") or s.get("homepage") or ""]
        for u in us:
            m = re.search(r"https?://([^/]+)", u if u.startswith("http") else "https://" + u)
            if m: domains.add(m.group(1).replace("www.", ""))
    listed = set()
    for r in rows:
        m = re.search(r"https?://([^/]+)", str(r["site"]))
        if m: listed.add(m.group(1).replace("www.", "").lower())
    both = domains & listed
    print(f"LEADERBOARD sellers with domain={len(domains)}, in bazaar={len(both)} -> earn-but-unlisted={len(domains-listed)}")
    with open(G("data/leaderboard_join.csv"), "w") as o:
        w = csv.writer(o); w.writerow(["seller_domain", "in_bazaar", "in_earn_without_list"])
        for dd in sorted(domains): w.writerow([dd, dd in listed, dd not in listed])
except Exception as e:
    print("leaderboard join skipped:", repr(e)[:80])

# ---------- price distribution ----------
pr = collections.Counter()
for r in rows:
    p = r["price"]
    b = "$0" if p == 0 else "<$0.001" if p < 0.001 else "$0.001-0.01" if p < 0.01 else "$0.01-0.10" if p < 0.1 else "$0.10-1" if p < 1 else "$1-10" if p < 10 else "$10+"
    pr[b] += 1
with open(G("data/prices.csv"), "w") as o:
    w = csv.writer(o); w.writerow(["band", "n"])
    for k in ["$0", "<$0.001", "$0.001-0.01", "$0.01-0.10", "$0.10-1", "$1-10", "$10+"]: w.writerow([k, pr.get(k, 0)])
print("price dist:", dict(pr))
print("DONE — CSVs in data/")
