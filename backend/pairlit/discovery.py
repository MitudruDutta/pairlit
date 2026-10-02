"""Discover candidates from live search and public cross-links; no fixed people or handles."""

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pairlit.sources import Apify, canonical, clean_source, identity_check
from pairlit.store import Store, now, uid


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", type=int, default=25)
    p.add_argument("--themes", default="creator,author,photographer,entrepreneur,designer,chef,speaker,artist")
    p.add_argument("--reuse", action="store_true")
    p.add_argument("--cached-only", action="store_true")
    args = p.parse_args()
    store = Store()
    api = Apify(store)

    def log(message):
        print(message, flush=True)

    queries = "\n".join(f'site:linkedin.com/in/ "instagram.com/" {theme.strip()}' for theme in args.themes.split(","))
    cached_ig = {}
    if args.reuse:
        with store.db() as c:
            saved = [json.loads(r[0]) for r in c.execute("SELECT data FROM runs")]
        datasets = [r for r in saved if r.get("status") == "SUCCEEDED" and r.get("defaultDatasetId")]

        def read(run):
            items = api.request(
                "GET", "datasets/" + run["defaultDatasetId"] + "/items", params={"clean": "true", "limit": 150}
            )
            for item in items:
                item["_pairlit_run"] = run["id"]
            return items

        rows = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for items in pool.map(read, datasets):
                for item in items:
                    if item.get("linkedinUrl") or item.get("publicIdentifier"):
                        rows.append(item)
                    elif item.get("username"):
                        cached_ig[item["username"].lower()] = item
        rows = list({row.get("linkedinUrl") or row.get("publicIdentifier"): row for row in rows}.values())
        li_run = ""
        log(json.dumps({"reused_linkedin_profiles": len(rows), "reused_instagram_profiles": len(cached_ig)}))
    else:
        search, run = api.run(
            "search",
            {"queries": queries, "maxPagesPerQuery": 2, "resultsPerPage": 20, "maximumLeadsEnrichmentRecords": 0},
            log,
        )
        urls = []
        for page in search:
            for hit in page.get("organicResults", []):
                try:
                    url = canonical(hit.get("url", ""), "linkedin")
                except ValueError:
                    continue
                if url not in urls:
                    urls.append(url)
        urls = urls[:110]
        log(json.dumps({"discovered_linkedin_urls": len(urls), "search_run": run}))
        Path("data/private/discovery.json").write_text(
            json.dumps({"queries": queries, "urls": urls, "search_run": run}, indent=2)
        )
        Path("data/private/discovery.json").chmod(0o600)
        if not urls:
            raise ValueError("Live search found no usable LinkedIn profiles")
        rows = []

        def scrape_batch(batch_urls):
            batch, run_id = api.run(
                "linkedin", {"urls": batch_urls, "profileScraperMode": "Profile details no email ($4 per 1k)"}
            )
            for row in batch:
                row["_pairlit_run"] = run_id
            return batch

        with ThreadPoolExecutor(max_workers=2) as pool:
            for batch in pool.map(scrape_batch, [urls[start : start + 10] for start in range(0, len(urls), 10)]):
                rows.extend(batch)
                log(json.dumps({"linkedin_profiles_read": len(rows)}))
        li_run = ""
    linked = []
    for row in rows:
        value = row.get("linkedinUrl") or row.get("url") or row.get("profileUrl") or row.get("inputUrl")
        if not value and row.get("publicIdentifier"):
            value = "https://www.linkedin.com/in/" + row["publicIdentifier"]
        try:
            li_url = canonical(value or "", "linkedin")
            li = clean_source("linkedin", row, li_url, row.get("_pairlit_run", li_run))
        except ValueError:
            continue
        # Only self-published LinkedIn profile data can supply this cross-link.
        own_data = " ".join(
            str(row.get(k, ""))
            for k in [
                "about",
                "summary",
                "headline",
                "websites",
                "website",
                "links",
                "contactInfo",
                "featured",
                "profileActions",
            ]
        )
        handles = list(
            dict.fromkeys(
                re.findall(r"instagram\.com/([A-Za-z0-9._]{1,30})", own_data)
                + re.findall(r"(?:Instagram|\bIG)\s*[:：-]\s*@([A-Za-z0-9._]{3,30})", own_data, re.I)
            )
        )
        for handle in handles:
            try:
                ig_url = canonical("https://www.instagram.com/" + handle, "instagram")
            except ValueError:
                continue
            if ig_url not in li["links"]:
                li["links"].append(ig_url)
            linked.append((li, ig_url))
    log(
        json.dumps(
            {
                "cross_linked_candidates": len(linked),
                "linkedin_results": len(rows),
                "sample_field_names": list(rows[0]) if rows else [],
            }
        )
    )
    Path("data/private/linked-candidates.json").write_text(json.dumps(linked, ensure_ascii=False))
    Path("data/private/linked-candidates.json").chmod(0o600)
    if not linked:
        raise ValueError("No Instagram links appeared in retrieved LinkedIn profiles")
    handles = list(dict.fromkeys(url.rstrip("/").split("/")[-1] for _, url in linked))[:100]
    missing = [h for h in handles if h not in cached_ig]
    insta, ig_run = (
        api.run("instagram", {"usernames": missing, "includeAboutSection": False}, log)
        if missing and not args.cached_only
        else ([], "")
    )
    by_handle = {**cached_ig, **{r.get("username", "").lower(): r for r in insta}}
    added = []
    rejected = []
    existing_records = {p["linkedin_url"]: p for p in store.all("profiles")}
    for li, ig_url in linked:
        if li["url"] in existing_records:
            saved = existing_records[li["url"]]
            store.patch(
                "profiles", saved["id"], location=li.get("location", ""), country_code=li.get("country_code", "")
            )
    existing = set(existing_records)
    for li, ig_url in linked:
        if len(store.all("profiles")) >= args.target:
            break
        if li["url"] in existing or any(p["linkedin_url"] == li["url"] for p in store.all("profiles")):
            continue
        try:
            row = by_handle.get(ig_url.rstrip("/").split("/")[-1], {})
            ig = clean_source("instagram", row, ig_url, row.get("_pairlit_run", ig_run))
            identity = identity_check(li, ig)
            # Public demonstration uses established public-facing creators, not a private-person directory.
            if not ig["verified_badge"] and int(ig.get("followers") or 0) < 10000:
                raise ValueError("Not an established public-facing demo account")
            if identity["name_tokens_matched"] < 2:
                raise ValueError("Cross-link requires matching public names for this demo")
            identity["status"] = "cross_linked"
            identity["explanation"] = "Public LinkedIn links to this Instagram; public names also match."
            record = {
                "id": uid(),
                "name": li["name"],
                "linkedin_url": li["url"],
                "instagram_url": ig_url,
                "sources": [li, ig],
                "identity": identity,
                "status": "sourced",
                "analysis": None,
                "portrait": ig["portrait"] or li["portrait"],
                "location": li.get("location", ""),
                "country_code": li.get("country_code", ""),
                "created_at": now(),
                "demo": True,
                "error": None,
            }
            store.put("profiles", record)
            existing.add(li["url"])
            added.append(record["id"])
            log(json.dumps({"admitted": record["name"], "profiles": len(added)}))
        except ValueError as exc:
            rejected.append({"linkedin_url": li["url"], "reason": str(exc)})
    Path("data/private/discovery-report.json").write_text(
        json.dumps({"admitted": len(added), "target": args.target, "rejected": rejected}, indent=2)
    )
    Path("data/private/discovery-report.json").chmod(0o600)
    log(
        json.dumps(
            {
                "admitted": len(added),
                "total_profiles": len(store.all("profiles")),
                "target_met": len(store.all("profiles")) >= args.target,
            }
        )
    )


if __name__ == "__main__":
    main()
