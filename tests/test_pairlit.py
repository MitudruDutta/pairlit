"""Contract and pipeline tests. Fictional fixtures never enter the live workspace."""

import time

import httpx
import pytest
from fastapi.testclient import TestClient
from pairlit.agents import Analysis, Trait, grounded, rank
from pairlit.api import create_app
from pairlit.engine import Engine
from pairlit.sources import Apify, canonical, clean_source, identity_check
from pairlit.store import Store

LI = "https://www.linkedin.com/in/fixture-person/"
IG = "https://www.instagram.com/fixture.person/"


def snapshots(name="Fixture Person"):
    return [
        clean_source(
            "linkedin",
            {
                "fullName": name,
                "about": "I design thoughtful products and mentor creative teams. Instagram: https://www.instagram.com/fixture.person/",
            },
            LI,
        ),
        clean_source(
            "instagram",
            {
                "username": "fixture.person",
                "fullName": name,
                "isPrivate": False,
                "biography": "Photography, books and long walks inspire my creative projects.",
            },
            IG,
        ),
    ]


def analysis(sources):
    return grounded(
        Analysis(
            summary="An unsupported biography",
            conversation_style="Curious about creative projects.",
            opening_question="What makes a photograph memorable?",
            unknowns=[],
            traits=[
                Trait(
                    category="priority",
                    label="Creative teams",
                    source="linkedin",
                    quote="mentor creative teams",
                    confidence="explicit",
                ),
                Trait(
                    category="quality",
                    label="Thoughtful design",
                    source="linkedin",
                    quote="design thoughtful products",
                    confidence="explicit",
                ),
                Trait(
                    category="interest",
                    label="Photography",
                    source="instagram",
                    quote="Photography, books and long walks",
                    confidence="explicit",
                ),
            ],
        ),
        sources,
    )


class Provider:
    def pair(self, li, ig, progress):
        progress("Reading both sources")
        s = snapshots()
        return s, identity_check(*s)


class Model:
    name = "test-only-model"

    def __init__(self):
        self.calls = []

    def analyze(self, profile):
        return analysis(profile["sources"])

    def turn(self, person, other, transcript, scenario, index):
        self.calls.append((person["id"], len(transcript)))
        return {
            "speaker_id": person["id"],
            "speaker": person["name"],
            "message": "Could we explore a bookshop and compare ideas about photography together?",
            "evidence_ids": [0],
            "fit": 72 if index % 2 == 0 else 61,
            "reflection": "A shared creative topic made this conversation interesting.",
            "curiosity": "How would our approaches differ?",
        }


def finish(engine):
    end = time.monotonic() + 5
    while any(j["status"] in ["queued", "running"] for j in engine.store.all("jobs")):
        assert time.monotonic() < end
        time.sleep(0.01)


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "test.db"))


@pytest.mark.parametrize(
    "url,platform",
    [
        ("http://www.linkedin.com/in/person/", "linkedin"),
        ("https://linkedin.com.attacker.example/in/person/", "linkedin"),
        ("https://user:pass@instagram.com/person/", "instagram"),
        ("https://instagram.com/p/123/", "instagram"),
        ("https://localhost/person/", "instagram"),
        ("https://www.linkedin.com/company/business/", "linkedin"),
        ("https://instagram.com:443/person/", "instagram"),
    ],
)
def test_reject_non_profile_urls(url, platform):
    with pytest.raises(ValueError):
        canonical(url, platform)


def test_canonical_and_private_visibility():
    assert canonical("https://uk.linkedin.com/in/Fixture-Person/?tracking=1", "linkedin") == LI
    for visibility in [True, None]:
        row = {
            "username": "fixture.person",
            "isPrivate": visibility,
            "biography": "Public text must not make a private account eligible.",
        }
        with pytest.raises(ValueError):
            clean_source("instagram", row, IG)
    with pytest.raises(ValueError):
        clean_source("instagram", {"username": "another", "isPrivate": False}, IG)


def test_identity_grounding_and_no_contact_enrichment():
    sources = snapshots()
    assert identity_check(*sources)["status"] == "cross_linked"
    assert "emails" not in sources[0] and "contactInfo" not in sources[0]
    result = analysis(sources)
    assert len(result["traits"]) == 3
    assert "unsupported" not in result["summary"]
    assert "not established" in result["unknowns"][0]
    broken = Analysis.model_validate(
        {
            **result,
            "traits": [{**t, "quote": "This statement never appeared in either source."} for t in result["traits"]],
        }
    )
    with pytest.raises(ValueError):
        grounded(broken, sources)
    sources[0]["links"] = []
    sources[0]["text"] = "A completely different professional."
    sources[1]["name"] = "Other Individual"
    with pytest.raises(ValueError):
        identity_check(*sources)


def test_api_full_pipeline_and_directional_rankings(store):
    model = Model()
    engine = Engine(store, model=model, provider=Provider())
    with TestClient(create_app(store, engine)) as client:
        assert client.get("/health").json()["product"] == "Pairlit"
        data = {"linkedin_url": LI, "instagram_url": IG, "permission": True}
        assert client.post("/api/profiles", json=data).status_code == 403
        assert (
            client.post(
                "/api/profiles", json={**data, "permission": False}, headers={"X-Pairlit-Client": "web"}
            ).status_code
            == 422
        )
        a = client.post("/api/profiles", json=data, headers={"X-Pairlit-Client": "web"}).json()
        finish(engine)
        assert store.get("profiles", a["id"])["status"] == "ready"
        assert client.post("/api/profiles", json=data, headers={"X-Pairlit-Client": "web"}).json()["id"] == a["id"]
        b = store.get("profiles", a["id"])
        b.update(
            id="second-fixture",
            name="Second Fixture",
            linkedin_url="https://www.linkedin.com/in/second-fixture/",
            instagram_url="https://www.instagram.com/second.fixture/",
        )
        store.put("profiles", b)
        before = client.get(f"/api/profiles/{a['id']}/rankings").json()
        assert len(before) == 1 and before[0]["basis"] == "profile_comparison"
        date_data = {
            "a_id": a["id"],
            "b_id": b["id"],
            "scenario": "A quiet bookshop café, discussing creative projects.",
        }
        d = client.post("/api/dates", json=date_data, headers={"X-Pairlit-Client": "web"}).json()
        finish(engine)
        saved = client.get("/api/dates/" + d["id"]).json()
        assert saved["status"] == "complete" and len(saved["turns"]) == 4
        assert model.calls == [(a["id"], 0), (b["id"], 1), (a["id"], 2), (b["id"], 3)]
        assert client.post("/api/dates", json=date_data, headers={"X-Pairlit-Client": "web"}).json()["id"] == d["id"]
        assert len(model.calls) == 4
        # Later profile analyses must not rewrite what informed an existing date.
        original = saved["agents"][a["id"]]["analysis"]
        replacement = {**original, "summary": "A later analysis of the same source snapshots."}
        store.patch("profiles", a["id"], analysis=replacement)
        assert client.get("/api/dates/" + d["id"]).json()["agents"][a["id"]]["analysis"] == original
        ra = rank(store, a["id"])
        rb = rank(store, b["id"])
        assert ra[0]["basis"] == "completed_date" and ra[0]["date_score"] == 72
        assert rb[0]["date_score"] == 61
        assert all(r["profile_id"] != a["id"] for r in ra)
        assert (
            client.post(
                "/api/dates", json={**date_data, "b_id": a["id"]}, headers={"X-Pairlit-Client": "web"}
            ).status_code
            == 422
        )
        assert client.get("/api/state").json()["stats"]["dates"] == 1
    engine.pool.shutdown()


def test_failed_date_resumes_only_missing_turns(store):
    model = Model()
    engine = Engine(store, model, Provider())
    for id in ["a", "b"]:
        s = snapshots()
        store.put(
            "profiles", {"id": id, "name": id, "status": "ready", "analysis": analysis(s), "portrait": "", "sources": s}
        )
    store.put(
        "dates",
        {
            "id": "resume",
            "a_id": "a",
            "b_id": "b",
            "scenario": "A creative afternoon in a bookshop café.",
            "status": "failed",
            "turns": [model.turn(store.get("profiles", "a"), store.get("profiles", "b"), [], "", 0)],
        },
    )
    model.calls.clear()
    engine.date("a", "b", "A creative afternoon in a bookshop café.")
    finish(engine)
    assert model.calls == [("b", 1), ("a", 2), ("b", 3)]
    assert store.get("dates", "resume")["status"] == "complete"
    engine.pool.shutdown()


def test_provider_run_reused_and_budget_enforced(store, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "test-only-not-a-real-token")
    monkeypatch.setenv("PAIRLIT_TOTAL_CAP_USD", ".1")
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "data": {"id": "run", "status": "SUCCEEDED", "defaultDatasetId": "dataset", "usageTotalUsd": 0.08}
                },
            )
        return httpx.Response(200, json=[{"fullName": "Fixture Person"}])

    a = Apify(store, httpx.Client(transport=httpx.MockTransport(handler)))
    payload = {"urls": [LI]}
    assert a.run("linkedin", payload)[1] == "run"
    assert a.run("linkedin", payload)[1] == "run"
    assert calls.count("POST") == 1
    with pytest.raises(ValueError, match="budget"):
        a.run("linkedin", {"urls": [LI + "different"]})


def test_chemistry_compares_both_sides_and_rank_averages_settings(store):
    from pairlit.agents import chemistry

    model = Model()
    engine = Engine(store, model, Provider())
    for id in ["a", "b"]:
        s = snapshots()
        store.put(
            "profiles", {"id": id, "name": id, "status": "ready", "analysis": analysis(s), "portrait": "", "sources": s}
        )
    engine.date("a", "b", "A quiet afternoon in a bookshop café.")
    finish(engine)
    second = engine.date("a", "b", "A photography walk where the agents negotiate a creative plan.")
    finish(engine)
    d = store.get("dates", second["id"])
    d["turns"][2]["fit"] = 40
    d["turns"][3]["fit"] = 85
    store.put("dates", d)
    comparison = chemistry(store, "a", "b")
    assert comparison["settings_tested"] == 2
    assert comparison["dates"][0]["mutual_fit"] == 61
    assert comparison["dates"][1]["mutual_fit"] == 40
    assert comparison["dates"][1]["assessment_gap"] == 45
    assert comparison["mutual_fit_range"] == 21
    ranking = rank(store, "a")[0]
    assert ranking["date_score"] == 56 and ranking["fit_range"] == [40, 72]
    assert ranking["settings_tested"] == 2
    with pytest.raises(ValueError):
        chemistry(store, "a", "a")
    engine.pool.shutdown()


def test_model_analysis_resolves_only_real_source_evidence(monkeypatch):
    from pairlit.agents import Model as LiveModel
    from pairlit.agents import Reading

    sources = snapshots()
    model = LiveModel()

    def generate(system, payload, schema, tokens):
        assert schema is Reading
        li = next(e for e in payload["evidence"] if e["source"] == "linkedin")
        ig = next(e for e in payload["evidence"] if e["source"] == "instagram")
        return Reading(
            summary="Unsupported summary is replaced",
            conversation_style="Curious",
            opening_question="What creative topic interests you?",
            unknowns=[],
            traits=[
                {"category": "priority", "label": "Creative teams", "evidence_id": li["id"], "confidence": "explicit"},
                {
                    "category": "quality",
                    "label": "Thoughtful design",
                    "evidence_id": li["id"],
                    "confidence": "suggested",
                },
                {"category": "interest", "label": "Photography", "evidence_id": ig["id"], "confidence": "explicit"},
            ],
        )

    monkeypatch.setattr(model, "generate", generate)
    result = model.analyze({"name": "Fixture Person", "sources": sources})
    assert len(result["traits"]) == 3
    for trait in result["traits"]:
        source = next(s for s in sources if s["platform"] == trait["source"])
        assert trait["quote"] in source["text"]
    assert "Unsupported" not in result["summary"]


def test_parallel_patches_preserve_independent_fields(store):
    from concurrent.futures import ThreadPoolExecutor

    store.put("jobs", {"id": "parallel", "status": "running"})
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: store.patch("jobs", "parallel", **{f"field_{i}": i}), range(16)))
    saved = store.get("jobs", "parallel")
    assert all(saved[f"field_{i}"] == i for i in range(16))
