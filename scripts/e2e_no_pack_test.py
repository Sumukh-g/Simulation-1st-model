"""Quick E2E check for no_pack runs."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def main():
    projects = get("/api/projects")["projects"]
    pid = projects[0]["id"]
    print("project", pid)

    body = {
        "prompt": "Reduce Delhi air pollution by 5% through transit and industry interventions",
        "simulation_mode": "no_pack",
        "project_id": pid,
        "max_scenarios": 40,
    }
    run = post("/api/runs/start", body)
    run_id = run["id"]
    print("started", run_id, run.get("status"))

    r = run
    for i in range(90):
        time.sleep(4)
        r = get(f"/api/runs/{run_id}")
        st = r.get("status")
        c = r.get("counters") or {}
        sm = c.get("scenarios_simulated", 0)
        cand = len(r.get("candidates") or [])
        summ = r.get("summary") or {}
        print(
            f"[{i}] status={st} sim={sm} cand={cand} "
            f"completed={summ.get('completed')} failed={summ.get('failed')} "
            f"budget={c.get('budget_consumed')}/{c.get('budget_total')}"
        )
        if st in ("completed", "failed", "awaiting_input"):
            break

    print(
        "FINAL",
        json.dumps(
            {
                "status": r.get("status"),
                "candidates": len(r.get("candidates") or []),
                "summary": r.get("summary"),
                "counters": r.get("counters"),
                "report_pdf": r.get("report_pdf"),
            },
            indent=2,
        ),
    )

    try:
        with urllib.request.urlopen(BASE + f"/api/runs/{run_id}/report.pdf", timeout=30) as resp:
            data = resp.read()
            print("PDF bytes", len(data), data[:4])
    except Exception as exc:
        print("PDF error", exc)


if __name__ == "__main__":
    main()
