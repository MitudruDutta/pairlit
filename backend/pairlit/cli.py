import argparse
import json
import time

from pairlit.engine import Engine
from pairlit.store import Store


def main():
    p = argparse.ArgumentParser(description="Pairlit administration")
    p.add_argument("command", choices=["serve", "analyze", "dates", "status"])
    p.add_argument("--all-pairs", action="store_true")
    p.add_argument("--limit", type=int, default=25)
    args = p.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("pairlit.api:create_app", factory=True, host="127.0.0.1", port=8000, access_log=False)
        return
    store = Store()
    if args.command == "status":
        print(
            json.dumps(
                {
                    "profiles": len(store.all("profiles")),
                    "ready": sum(p["status"] == "ready" for p in store.all("profiles")),
                    "dates": len(store.all("dates")),
                }
            )
        )
        return
    engine = Engine(store)
    if args.command == "analyze":
        for profile in store.all("profiles")[: args.limit]:
            if profile["status"] != "ready":
                engine.analyze(profile["id"])
    elif args.command == "dates":
        engine.round(args.all_pairs)
    while True:
        jobs = store.all("jobs")
        active = [j for j in jobs if j["status"] in ["running", "queued"]]
        print(
            json.dumps(
                {
                    "running": len(active),
                    "complete": sum(j["status"] == "complete" for j in jobs),
                    "failed": sum(j["status"] == "failed" for j in jobs),
                }
            ),
            flush=True,
        )
        if not active:
            break
        time.sleep(10)
    engine.pool.shutdown()


if __name__ == "__main__":
    main()
