import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from pairlit.agents import chemistry, rank
from pairlit.engine import Engine
from pairlit.store import Store


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    linkedin_url: str = Field(max_length=250)
    instagram_url: str = Field(max_length=150)
    permission: bool


class DateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a_id: str = Field(max_length=40)
    b_id: str = Field(max_length=40)
    scenario: str = Field(
        default="A bookshop café. Choose a book for one another, then plan a relaxed afternoon together.",
        min_length=20,
        max_length=400,
    )


def create_app(store=None, engine=None):
    store = store or Store()
    engine = engine or Engine(store)

    @asynccontextmanager
    async def lifespan(app):
        for job in store.all("jobs"):
            if job["status"] in ["queued", "running"]:
                store.patch("jobs", job["id"], status="failed", error="Server restarted; retry resumes saved work.")
                table = "dates" if job["kind"] == "date" else "profiles"
                store.patch(table, job["target"], status="failed", error="Interrupted by restart; retry to continue.")
        yield

    app = FastAPI(title="Pairlit", lifespan=lifespan)
    rate = defaultdict(deque)
    lock = threading.Lock()

    @app.middleware("http")
    async def boundaries(request, call_next):
        if request.method == "POST":
            try:
                length = int(request.headers.get("content-length", "0") or 0)
            except ValueError:
                length = 10001
            if length > 10000:
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "Request too large"}, status_code=413)
            if request.headers.get("x-pairlit-client") != "web":
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "Pairlit client header required"}, status_code=403)
            with lock:
                q = rate[request.client.host if request.client else "local"]
                clock = time.monotonic()
                while q and q[0] < clock - 60:
                    q.popleft()
                if len(q) >= 12:
                    from fastapi.responses import JSONResponse

                    return JSONResponse({"detail": "Please wait one minute before starting more work"}, status_code=429)
                q.append(clock)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/health")
    def health():
        return {"status": "ok", "product": "Pairlit", "storage": "sqlite"}

    @app.get("/api/state")
    def state():
        profiles = store.all("profiles")
        dates = store.all("dates")
        jobs = store.all("jobs")
        return {
            "profiles": profiles,
            "dates": dates,
            "jobs": jobs[-150:],
            "stats": {
                "profiles": len(profiles),
                "ready": sum(p["status"] == "ready" for p in profiles),
                "dates": sum(d["status"] == "complete" for d in dates),
                "active": sum(j["status"] in ["queued", "running"] for j in jobs),
            },
            "model": engine.model.name,
            "source_policy": "Exactly LinkedIn and public Instagram. Public-profile simulations; no real-world participation implied.",
        }

    @app.post("/api/profiles", status_code=202)
    def create(data: ProfileInput):
        if not data.permission:
            raise ValueError("Confirm matching public accounts and acknowledge the fictional simulation")
        return engine.create_profile(data.linkedin_url, data.instagram_url)

    @app.get("/api/profiles/{id}")
    def profile(id: str):
        return store.get("profiles", id)

    @app.get("/api/profiles/{id}/portrait")
    def portrait(id: str):
        store.get("profiles", id)
        root = Path("data/private/portraits")
        path = root / (id + ".image")
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path, media_type=(root / (id + ".mime")).read_text())

    @app.post("/api/profiles/{id}/analyze", status_code=202)
    def analyze(id: str):
        return engine.analyze(id)

    @app.post("/api/dates", status_code=202)
    def start(data: DateInput):
        return engine.date(data.a_id, data.b_id, data.scenario)

    @app.get("/api/dates/{id}")
    def date(id: str):
        return store.get("dates", id)

    @app.get("/api/profiles/{id}/rankings")
    def rankings(id: str):
        return rank(store, id)

    @app.get("/api/chemistry/{a_id}/{b_id}")
    def compare(a_id: str, b_id: str):
        return chemistry(store, a_id, b_id)

    @app.post("/api/round", status_code=202)
    def round():
        return {"date_ids": engine.round()}

    root = Path("apps/web/out")
    if root.exists():
        app.mount("/_next", StaticFiles(directory=root / "_next"), name="next")

        @app.get("/")
        def index():
            return FileResponse(root / "index.html")

        @app.get("/favicon.ico")
        def favicon():
            raise HTTPException(404)

    return app
