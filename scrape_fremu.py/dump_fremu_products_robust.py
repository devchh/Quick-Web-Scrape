# dump_fremu_products_robust.py
import csv, time, math, random
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

BASE = "https://fremu.co.uk/wp-json/wc/store/products"
PER_PAGE = 60  # smaller than 100 to reduce payload; adjust if needed
TIMEOUT = 25

def make_session():
    s = requests.Session()
    # Retry on connection drops and transient 5xx/CDN errors
    retry = Retry(
        total=8,
        connect=8,
        read=8,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504, 520, 521, 522, 523, 524),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=16)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) Python/requests FremuCatalogDump/1.0",
        "Accept": "application/json",
        "Connection": "keep-alive",
    })
    return s

def fetch_page(session, page):
    # small jitter to avoid burst hits
    time.sleep(0.2 + random.random() * 0.4)
    r = session.get(
        BASE,
        params={"per_page": PER_PAGE, "page": page},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    total = int(r.headers.get("X-WP-Total", "0"))
    total_pages = int(r.headers.get("X-WP-TotalPages", "0"))
    return data, total, total_pages

def price_to_decimal(p_minor, minor_units=2):
    if not p_minor:
        return ""
    return f"{int(p_minor) / (10 ** minor_units):.2f}"

def row_from_item(it):
    prices = it.get("prices") or {}
    imgs = it.get("images") or []
    cats = it.get("categories") or []
    return {
        "id": it.get("id"),
        "name": it.get("name"),
        "slug": it.get("slug"),
        "sku": it.get("sku") or "",
        "price": price_to_decimal(prices.get("price"), prices.get("currency_minor_unit", 2)),
        "currency": prices.get("currency_code", "GBP"),
        "on_sale": it.get("on_sale"),
        "in_stock": it.get("is_in_stock"),
        "permalink": it.get("permalink"),
        "image": imgs[0].get("src") if imgs else "",
        "categories": " | ".join(c.get("name","") for c in cats),
    }

def main():
    session = make_session()

    # First page to discover totals. Fall back if headers missing.
    data, total, total_pages = fetch_page(session, 1)
    if total_pages == 0:
        # Fallback strategy: keep paging until we hit an empty page
        total_pages = 1
        while True:
            nxt, _, _ = fetch_page(session, total_pages)
            if not nxt:
                break
            if total_pages > 1:
                data += nxt if total_pages == 2 else nxt  # first page already in `data`
            total_pages += 1
        total_pages -= 1  # we overshot by one
        total = len(data)

    print(f"Discovered {total} products across {total_pages} pages (per_page={PER_PAGE}).")

    cols = ["id","name","slug","sku","price","currency","on_sale","in_stock","permalink","image","categories"]
    with open("fremu_products.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()

        # write first page
        for it in data:
            w.writerow(row_from_item(it))

        # remaining pages
        for page in range(2, total_pages + 1):
            page_data, *_ = fetch_page(session, page)
            for it in page_data:
                w.writerow(row_from_item(it))
            # extra jitter between pages
            time.sleep(0.2 + random.random() * 0.4)

    print("Saved to fremu_products.csv")

if __name__ == "__main__":
    main()
