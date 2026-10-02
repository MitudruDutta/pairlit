import threading
from concurrent.futures import ThreadPoolExecutor

from pairlit.agents import Model, rank
from pairlit.sources import Apify, canonical
from pairlit.store import now, uid


class Engine:
    def __init__(self, store, model=None, provider=None):
        self.store = store
        self.model = model or Model()
        self.provider = provider
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pairlit")
        self.lock = threading.Lock()

    def submit(self, kind, target, fn):
        with self.lock:
            current = next(
                (
                    j
                    for j in self.store.all("jobs")
                    if j["kind"] == kind and j["target"] == target and j["status"] in ["queued", "running"]
                ),
                None,
            )
            if current:
                return current
            job = {
                "id": uid(),
                "kind": kind,
                "target": target,
                "status": "queued",
                "progress": "Waiting for an agent…",
                "created_at": now(),
                "error": None,
            }
            self.store.put("jobs", job)

        def work():
            try:
                self.store.patch("jobs", job["id"], status="running", progress="Starting…")
                fn(lambda message: self.store.patch("jobs", job["id"], progress=message))
                self.store.patch("jobs", job["id"], status="complete", progress="Complete")
            except Exception as exc:
                safe = (
                    str(exc) if isinstance(exc, ValueError) else "Operation failed. Check local service logs and retry."
                )
                self.store.patch("jobs", job["id"], status="failed", error=safe, progress="Needs attention")
                table = "dates" if kind == "date" else "profiles"
                self.store.patch(table, target, status="failed", error=safe)

        self.pool.submit(work)
        return job

    def create_profile(self, linkedin_url, instagram_url):
        li = canonical(linkedin_url, "linkedin")
        ig = canonical(instagram_url, "instagram")
        with self.lock:
            existing = next(
                (p for p in self.store.all("profiles") if p["linkedin_url"] == li and p["instagram_url"] == ig), None
            )
            if existing:
                return existing
            if len(self.store.all("profiles")) >= 150:
                raise ValueError("Workspace profile limit reached")
            p = {
                "id": uid(),
                "name": li.rstrip("/").split("/")[-1].replace("-", " ").title(),
                "linkedin_url": li,
                "instagram_url": ig,
                "status": "queued",
                "sources": [],
                "analysis": None,
                "portrait": "",
                "identity": None,
                "created_at": now(),
                "error": None,
                "demo": False,
            }
            self.store.put("profiles", p)
        self.analyze(p["id"])
        return p

    def analyze(self, id):
        self.store.get("profiles", id)

        def run(progress):
            p = self.store.get("profiles", id)
            if not p["sources"]:
                self.store.patch("profiles", id, status="reading", error=None)
                sources, identity = (self.provider or Apify(self.store)).pair(
                    p["linkedin_url"], p["instagram_url"], progress
                )
                p = self.store.patch(
                    "profiles",
                    id,
                    sources=sources,
                    identity=identity,
                    name=sources[0]["name"],
                    portrait=sources[1]["portrait"] or sources[0]["portrait"],
                )
            self.store.patch("profiles", id, status="analyzing", error=None)
            progress("Reading both sources and grounding profile traits…")
            analysis = self.model.analyze(p)
            self.store.patch("profiles", id, status="ready", analysis=analysis)

        return self.submit("profile", id, run)

    def date(
        self,
        a_id,
        b_id,
        scenario="A bookshop café. Choose a book for one another, then plan a relaxed afternoon together.",
    ):
        if a_id == b_id:
            raise ValueError("Choose two different agents")
        a = self.store.get("profiles", a_id)
        b = self.store.get("profiles", b_id)
        if a["status"] != "ready" or b["status"] != "ready":
            raise ValueError("Both profiles must finish analysis first")
        with self.lock:
            pair = sorted([a_id, b_id])
            existing = next(
                (
                    d
                    for d in self.store.all("dates")
                    if sorted([d["a_id"], d["b_id"]]) == pair and d["scenario"] == scenario
                ),
                None,
            )
            if existing and existing["status"] in ["queued", "running", "complete"]:
                return existing
            d = existing or {
                "id": uid(),
                "a_id": a_id,
                "b_id": b_id,
                "scenario": scenario,
                "turns": [],
                "created_at": now(),
            }
            if not d.get("agents"):
                d["agents"] = {p["id"]: {k: p.get(k) for k in ["id", "name", "portrait", "analysis"]} for p in [a, b]}
            a = {**a, "analysis": d["agents"][a_id]["analysis"]}
            b = {**b, "analysis": d["agents"][b_id]["analysis"]}
            d.update(status="queued", error=None)
            self.store.put("dates", d)

        def run(progress):
            self.store.patch("dates", d["id"], status="running")
            turns = self.store.get("dates", d["id"])["turns"]
            for i in range(len(turns), 4):
                actor, partner = (a, b) if i % 2 == 0 else (b, a)
                progress(actor["name"] + "’s agent is considering its next move…")
                turn = self.model.turn(actor, partner, turns, scenario, i)
                turns = turns + [turn]
                self.store.patch("dates", d["id"], turns=turns)
            self.store.patch("dates", d["id"], status="complete", finished_at=now())

        self.submit("date", d["id"], run)
        return d

    def round(self, all_pairs=False):
        ready = [p for p in self.store.all("profiles") if p["status"] == "ready"]
        if len(ready) < 2:
            raise ValueError("At least two analyzed profiles are required")
        if all_pairs:
            pairs = [(a, b) for i, a in enumerate(ready) for b in ready[i + 1 :]]
        else:
            # ponytail: rank public themes, explore one different perspective; embeddings can replace lexical overlap later.
            by_id = {p["id"]: p for p in ready}
            pairs = []
            for person in ready:
                candidates = rank(self.store, person["id"])
                for candidate in [candidates[0], candidates[-1]]:
                    pairs.append((person, by_id[candidate["profile_id"]]))
        return list(dict.fromkeys(self.date(a["id"], b["id"])["id"] for a, b in pairs))
