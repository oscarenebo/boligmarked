import time
import csv
import math
from typing import List, Dict, Optional
import requests
import os

BASE_PAGE = "https://www.boliga.dk/salg/resultater?searchTab=1&page=1&sort=date-d&saleType=1"
API_URL = "https://api.boliga.dk/api/v2/sold/search/results"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "da,en;q=0.9",
    "Referer": "https://www.boliga.dk/",
    "Origin": "https://www.boliga.dk",
}


def _get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    s.get(BASE_PAGE, timeout=20)
    return s


def append_rows_to_csv(data: List[Dict], filename: str):
    """Append rows to CSV, create file + header if needed."""
    if not data:
        return
    file_exists = os.path.exists(filename) and os.path.getsize(filename) > 0
    fieldnames = list(data[0].keys())
    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(data)
    print(f"💾 Appended {len(data)} rows to {filename}")


def scrape_boliga(
    search_tab: int = 1,
    sale_type: int = 1,
    sort: str = "date-a",         # default to oldest → newest now
    filters: Optional[Dict] = None,
    start_page: int = 1,
    end_page: Optional[int] = None,  # if None → we’ll discover the real last page
    sleep: float = 1.0,
    debug: bool = False,
    max_retries_per_page: int = 15,
    output_file: Optional[str] = None,  # if set → periodic disk writes
    save_every: int = 10,
) -> List[Dict]:
    session = _get_session()

    base_params = {
        "searchTab": search_tab,
        "saleType": sale_type,
        "sort": sort,
    }
    if filters:
        base_params.update(filters)

    all_rows: List[Dict] = []
    pending_rows: List[Dict] = []
    total_saved_to_disk = 0

    page = start_page
    discovered_end_page = None  # we'll fill this when we see "total" the first time

    while True:
        # if user gave an explicit end_page, obey that
        if end_page and page > end_page:
            break
        # if we discovered the last page from API, obey that too
        if discovered_end_page and page > discovered_end_page:
            break

        params = dict(base_params)
        params["page"] = page

        # retry loop
        for attempt in range(max_retries_per_page):
            try:
                resp = session.get(API_URL, params=params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.HTTPError as e:
                status = e.response.status_code
                if status == 429 or 500 <= status < 600:
                    wait = (attempt + 1) * 0.5
                    print(f"⚠️ Got {status} on page {page}, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                else:
                    raise
        else:
            print(f"❌ Failed to fetch page {page} after {max_retries_per_page} retries.")
            break

        # discover total pages on the first successful page
        if page == start_page:
            total = data.get("total")
            page_size = data.get("pageSize", 50)
            if total:
                discovered_end_page = math.ceil(total / page_size)
                # if user gave no end_page, we’ll just go to discovered_end_page
                print(
                    f"📄 API reports {total:,} listings with page size {page_size} → "
                    f"{discovered_end_page} pages available"
                )

        results = data.get("result") or data.get("results") or []
        if not results:
            if debug:
                print(f"⚠️ Page {page} was empty — stopping.")
                print(str(data)[:500])
            break

        for item in results:
            row = {
                "address": item.get("address"),
                "zipcode": item.get("zipCode"),
                "price": item.get("price"),
                "soldDate": item.get("soldDate"),
                "propertyType": item.get("propertyType"),
                "saleType": item.get("saleType"),
                "sqmPrice": item.get("sqmPrice"),
                "rooms": item.get("rooms"),
                "size": item.get("size"),
                "buildYear": item.get("buildYear"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "guid": item.get("guid"),
            }
            all_rows.append(row)
            if output_file:
                pending_rows.append(row)

        print(f"✅ Fetched page {page} ({len(results)} rows)")

        # periodic flush — count pages relative to start_page
        if output_file and save_every and ((page - start_page + 1) % save_every == 0):
            try:
                append_rows_to_csv(pending_rows, output_file)
                total_saved_to_disk += len(pending_rows)
                print(
                    f"💾 Flushed buffer after page {page} "
                    f"({len(pending_rows)} rows) — total saved: {total_saved_to_disk}"
                )
                pending_rows.clear()
            except Exception as e:
                print(f"⚠️ Failed to append to {output_file}: {e}")

        page += 1
        time.sleep(sleep)

    # final flush
    if output_file and pending_rows:
        try:
            append_rows_to_csv(pending_rows, output_file)
            total_saved_to_disk += len(pending_rows)
            print(
                f"💾 Final flush ({len(pending_rows)} rows) — total saved: {total_saved_to_disk}"
            )
            pending_rows.clear()
        except Exception as e:
            print(f"⚠️ Failed to append final rows to {output_file}: {e}")

    print(f"✅ Total rows fetched (in memory): {len(all_rows)}")
    if output_file:
        print(f"💾 Total rows saved to disk: {total_saved_to_disk}")
    return all_rows


def save_to_csv(data: List[Dict], filename: str):
    """Full rewrite helper — only use if you did NOT do periodic flushes."""
    if not data:
        print("⚠️ No data to save.")
        return
    fieldnames = list(data[0].keys())
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"💾 Saved {len(data)} rows to {filename}")
