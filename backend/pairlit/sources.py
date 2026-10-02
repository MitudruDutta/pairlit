"""Two-source ingestion. Discovery snippets never enter profile analysis."""

import hashlib
import json
import os
import re
import time
import unicodedata
from urllib.parse import urlsplit

import httpx

from pairlit.store import now

ACTORS = {
    "linkedin": "harvestapi~linkedin-profile-scraper",
    "instagram": "apify~instagram-profile-scraper",
    "search": "apify~google-search-scraper",
}


def canonical(value, platform):
    try:
        u = urlsplit(value.strip())
    except ValueError:
        raise ValueError("Invalid profile URL") from None
    if u.scheme != "https" or u.username or u.password or u.port:
        raise ValueError("Use a public HTTPS profile URL")
    host = (u.hostname or "").lower()
    if platform == "linkedin":
        if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
            raise ValueError("LinkedIn URL required")
        match = re.fullmatch(r"/in/([A-Za-z0-9%_-]{2,120})/?", u.path)
        if not match:
            raise ValueError("Use an individual LinkedIn /in/ profile")
        return "https://www.linkedin.com/in/" + match[1].lower() + "/"
    if host not in ["instagram.com", "www.instagram.com"]:
        raise ValueError("Instagram URL required")
    match = re.fullmatch(r"/([A-Za-z0-9._]{1,30})/?", u.path)
    if not match or match[1].lower() in ["p", "reel", "reels", "stories", "explore", "accounts", "direct"]:
        raise ValueError("Use an Instagram profile, not a post or login page")
    return "https://www.instagram.com/" + match[1].lower() + "/"


def text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text(x) for x in value)
    if isinstance(value, dict):
        return "\n".join(
            text(v)
            for k, v in value.items()
            if k
            in [
                "title",
                "name",
                "description",
                "companyName",
                "skill",
                "schoolName",
                "text",
                "caption",
                "url",
                "link",
                "website",
            ]
        )
    return ""


def normalize_name(value):
    return set(
        re.findall(r"[a-z]{3,}", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower())
    )


def clean_source(kind, row, url, run_id=""):
    if row.get("error") or row.get("errorDescription"):
        raise ValueError(kind + " profile could not be retrieved")
    if kind == "instagram":
        if row.get("private") is True or row.get("isPrivate") is True:
            raise ValueError("Instagram account is private")
        if row.get("private") is not False and row.get("isPrivate") is not False:
            raise ValueError("Instagram public visibility could not be verified")
        username = row.get("username", "")
        if username.lower() != url.rstrip("/").split("/")[-1]:
            raise ValueError("Instagram response identity differs from requested profile")
        name = row.get("fullName") or row.get("full_name") or username
        chunks = [row.get("biography", "")]
        for p in row.get("latestPosts", [])[:12]:
            if not p.get("ownerUsername") or p["ownerUsername"].lower() == username.lower():
                chunks.append(p.get("caption", ""))
        content = "\n\n".join(x for x in chunks if isinstance(x, str))[:18000]
        portrait = row.get("profilePicUrlHD") or row.get("profilePicUrl", "")
        links = [row.get("externalUrl", "")] + [
            x.get("url", "") for x in row.get("externalUrls", []) if isinstance(x, dict)
        ]
        verified = bool(row.get("verified") or row.get("isVerified"))
        followers = row.get("followersCount", 0)
    else:
        name = (
            row.get("fullName")
            or row.get("name")
            or " ".join([row.get("firstName", ""), row.get("lastName", "")]).strip()
        )
        if not name:
            raise ValueError("LinkedIn profile has no verifiable name")
        actual = row.get("linkedinUrl") or row.get("url") or row.get("profileUrl")
        if actual and canonical(actual, "linkedin") != url:
            raise ValueError("LinkedIn returned a different profile URL")
        fields = [
            "headline",
            "about",
            "summary",
            "experience",
            "education",
            "skills",
            "interests",
            "publications",
            "projects",
            "websites",
            "website",
            "featured",
            "profileActions",
        ]
        content = "\n\n".join(text(row.get(k, "")) for k in fields)[:18000]
        portrait = row.get("photo") or row.get("profilePicture") or row.get("profilePicUrl") or ""
        if isinstance(portrait, dict):
            portrait = portrait.get("url", "")
        links = re.findall(r'https?://[^\s"<>]+', text(row.get("websites", [])) + " " + content)
        for field in ["links", "contactInfo"]:
            links.extend(
                "https://www.instagram.com/" + h + "/"
                for h in re.findall(r"instagram\.com/([A-Za-z0-9._]{1,30})", str(row.get(field, "")))
            )
        verified = False
        followers = row.get("followersCount", 0)
    content = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[contact omitted]", content)
    content = re.sub(
        r"\+?\d[\d ().-]{7,}\d",
        lambda m: "[contact omitted]" if sum(c.isdigit() for c in m[0]) >= 10 else m[0],
        content,
    )
    if len(content.strip()) < 30:
        raise ValueError(kind + " returned too little public text to analyze")
    location = row.get("location", {}) if kind == "linkedin" else {}
    public_location = (
        location.get("linkedinText", "")
        if isinstance(location, dict)
        else location
        if isinstance(location, str)
        else ""
    )
    country_code = location.get("countryCode", "") if isinstance(location, dict) else ""
    return {
        "location": public_location[:150],
        "country_code": country_code,
        "platform": kind,
        "url": url,
        "name": name,
        "text": content,
        "portrait": portrait if isinstance(portrait, str) and portrait.startswith("https://") else "",
        "links": links,
        "public": True,
        "verified_badge": verified,
        "followers": followers,
        "fetched_at": now(),
        "run_id": run_id,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
    }


def identity_check(li, ig):
    shared = normalize_name(li["name"]) & normalize_name(ig["name"])
    linked = ig["url"].rstrip("/").lower() in li["text"].lower() or any(
        ig["url"].rstrip("/").lower() in str(x).lower() for x in li["links"]
    )
    if len(shared) < 2 and not linked:
        raise ValueError("Account identity is uncertain: the two public names do not match")
    return {
        "status": "cross_linked" if linked else "name_match_review",
        "explanation": "LinkedIn links to this Instagram account."
        if linked
        else "Public names match. Official account ownership still needs review.",
        "name_tokens_matched": len(shared),
    }


class Apify:
    def __init__(self, store, client=None):
        self.store = store
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)
        token = os.getenv("APIFY_TOKEN")
        if not token:
            raise ValueError("Apify is not configured on this server")
        self.headers = {"Authorization": "Bearer " + token}

    def request(self, method, path, **kwargs):
        r = self.client.request(method, "https://api.apify.com/v2/" + path, headers=self.headers, **kwargs)
        if r.status_code >= 300:
            raise ValueError(f"Apify request failed ({r.status_code}); check provider access or budget")
        if len(r.content) > 12000000:
            raise ValueError("Provider response exceeds size limit")
        return r.json()

    def run(self, kind, payload, progress=lambda _: None):
        fp = hashlib.sha256(json.dumps([ACTORS[kind], payload], sort_keys=True).encode()).hexdigest()
        cap = min(
            float(os.getenv("PAIRLIT_RUN_CAP_USD", ".50")),
            0.08
            if kind == "linkedin" and len(payload.get("urls", [])) <= 10
            else min(0.5, 0.025 + 0.004 * len(payload.get("usernames", [])))
            if kind == "instagram"
            else 0.5,
        )
        total = float(os.getenv("PAIRLIT_TOTAL_CAP_USD", "2"))
        with self.store.db() as c:
            c.execute("BEGIN IMMEDIATE")
            saved = c.execute("SELECT data FROM runs WHERE fingerprint=?", (fp,)).fetchone()
            if saved:
                run = json.loads(saved[0])
            else:
                spent = c.execute("SELECT coalesce(sum(cap),0) FROM runs").fetchone()[0]
                if spent + cap > total:
                    raise ValueError("Extraction budget reached. Operator must review usage before another run.")
                run = {"status": "STARTING", "kind": kind, "created_at": now()}
                c.execute("INSERT INTO runs VALUES (?,?,?)", (fp, json.dumps(run), cap))
        if run["status"] == "STARTING" and saved:
            raise ValueError("An earlier provider start has an uncertain outcome; operator review required")
        if not saved:
            run = self.request(
                "POST",
                "acts/" + ACTORS[kind] + "/runs",
                params={"maxTotalChargeUsd": cap, "timeout": 600, "maxItems": 150},
                json=payload,
            )["data"]
            run = {k: run.get(k) for k in ["id", "status", "defaultDatasetId", "usageTotalUsd"]}
            with self.store.db() as c:
                c.execute("UPDATE runs SET data=? WHERE fingerprint=?", (json.dumps(run), fp))
        deadline = time.monotonic() + 630
        while run["status"] not in ["SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"]:
            if time.monotonic() > deadline:
                raise ValueError("Provider is still running. Retry uses the existing run.")
            progress("Reading " + kind + " public profiles…")
            time.sleep(3)
            raw = self.request("GET", "actor-runs/" + run["id"])["data"]
            run = {k: raw.get(k) for k in ["id", "status", "defaultDatasetId", "usageTotalUsd"]}
            with self.store.db() as c:
                c.execute(
                    "UPDATE runs SET data=?,cap=? WHERE fingerprint=?",
                    (
                        json.dumps(run),
                        (
                            float(raw.get("usageTotalUsd") or 0)
                            if raw["status"] in ["SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"]
                            else cap
                        ),
                        fp,
                    ),
                )
        if run["status"] != "SUCCEEDED":
            raise ValueError(kind + " extraction ended " + run["status"])
        with self.store.db() as c:
            c.execute("UPDATE runs SET cap=? WHERE fingerprint=?", (float(run.get("usageTotalUsd") or 0), fp))
        rows = self.request(
            "GET", "datasets/" + run["defaultDatasetId"] + "/items", params={"clean": "true", "limit": 150}
        )
        return rows, run["id"]

    def pair(self, li, ig, progress=lambda _: None):
        li = canonical(li, "linkedin")
        ig = canonical(ig, "instagram")
        a, ar = self.run(
            "linkedin", {"urls": [li], "profileScraperMode": "Profile details no email ($4 per 1k)"}, progress
        )
        b, br = self.run(
            "instagram", {"usernames": [ig.rstrip("/").split("/")[-1]], "includeAboutSection": False}, progress
        )
        if len(a) != 1 or len(b) != 1:
            raise ValueError("Expected exactly one result from each account")
        sources = [clean_source("linkedin", a[0], li, ar), clean_source("instagram", b[0], ig, br)]
        return sources, identity_check(*sources)
