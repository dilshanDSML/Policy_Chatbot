import argparse
import asyncio
import getpass
import json
import os
import statistics
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.test_case import LLMTestCase
from dotenv import load_dotenv
from redis.asyncio import Redis

try:
    from .groq_judge import GroqJudge
except ImportError:
    from groq_judge import GroqJudge


root = Path(__file__).resolve().parents[1]
load_dotenv(root / ".env")
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGSMITH_TRACING", "true").lower()
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "policybot")
api_url = os.getenv("POLICYBOT_URL", "http://localhost:8000")
results_folder = root / "eval" / "results"
dataset_path = root / "eval" / "dataset.json"
strategies = ["hybrid_rerank"]


def make_metrics(judge):
    settings = {"model": judge, "threshold": 0.5, "include_reason": True, "async_mode": False}
    return {
        "answer_relevancy": AnswerRelevancyMetric(**settings),
        "faithfulness": FaithfulnessMetric(**settings),
        "contextual_relevancy": ContextualRelevancyMetric(**settings),
        "contextual_precision": ContextualPrecisionMetric(**settings),
        "contextual_recall": ContextualRecallMetric(**settings),
    }


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    return round(values[max(0, min(len(values) - 1, int((len(values) - 1) * fraction)))], 2)


# ---- Bookmark helpers (new) -------------------------------------------------
# The "progress file" remembers every finished question, so the next run
# skips them and continues from where the last run stopped.

def is_rate_limit(error):
    # True when the error text looks like "daily limit reached" (HTTP 429).
    text = str(error).lower()
    return "429" in text or "rate limit" in text or "rate_limit" in text or "ratelimit" in text


def load_progress(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"sessions": {}, "records": {}}


def save_progress(path, progress):
    # Write to a temp file first, then swap, so a crash never leaves a broken file.
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    temp_path.replace(path)
# -----------------------------------------------------------------------------


async def login(client):
    email = input("Admin email: ").strip()
    password = getpass.getpass("Admin password: ")
    response = await client.post("/login", json={"email": email, "password": password})
    response.raise_for_status()
    return response.json()["access_token"]


async def clear_answer_cache():
    redis = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    try:
        keys = [key async for key in redis.scan_iter("answer:*")]
        if keys:
            await redis.delete(*keys)
    finally:
        await redis.aclose()


async def run_one(client, token, case, strategy):
    session_id = str(uuid.uuid4())
    response = await client.post(
        "/ask",
        headers={"Authorization": "Bearer " + token},
                    json={"question": case["question"], "session_id": session_id, "retrieval_config": strategy, "include_contexts": True},
    )
    response.raise_for_status()
    output = response.json()
    warm = None
    if not case.get("session"):
        warm_response = await client.post(
            "/ask",
            headers={"Authorization": "Bearer " + token},
                        json={"question": case["question"], "session_id": str(uuid.uuid4()), "retrieval_config": strategy, "include_contexts": True},
        )
        warm_response.raise_for_status()
        warm = warm_response.json()
    test_case = LLMTestCase(
        input=case["question"],
        actual_output=output["answer"],
        expected_output=case["expected_answer"],
        retrieval_context=output.get("contexts", []),
    )
    return output, warm, test_case


async def main():
    parser = argparse.ArgumentParser(description="Run PolicyBot's five DeepEval RAG metrics.")
    parser.add_argument("--dry-run", action="store_true", help="Check the dataset and metric setup without API calls.")
    parser.add_argument("--limit", type=int, default=0, help="Limit cases for a quick smoke evaluation.")
    parser.add_argument("--fresh", action="store_true", help="Delete the saved progress and start from question 1.")
    parser.add_argument("--rescore", action="store_true", help="Score again only the metrics whose saved score is empty. Does not ask the app again.")
    args = parser.parse_args()

    with dataset_path.open(encoding="utf-8") as file:
        cases = json.load(file)
    if args.limit:
        cases = cases[:args.limit]
    if args.dry_run:
        print(f"Dataset OK: {len(cases)} policy questions; evaluation mode: hybrid_rerank.")
        print("Metrics: answer relevancy, faithfulness, contextual relevancy, contextual precision, contextual recall.")
        return

    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise SystemExit("Add GROQ_API_KEY to D:\\Policybot\\.env first.")
    judge = GroqJudge(key, model_name="openai/gpt-oss-120b")
    configs = strategies
    results_folder.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(base_url=api_url, timeout=180) as client:
        token = await login(client)
        for strategy in configs:
            await clear_answer_cache()
            metrics = make_metrics(judge)

            progress_path = results_folder / f"progress_{strategy}.json"
            if args.fresh and progress_path.exists():
                progress_path.unlink()
                print("Old progress deleted. Starting from question 1.")
            progress = load_progress(progress_path)
            print(f"Already saved from earlier runs: {len(progress['records'])} question(s).")
            stop_run = False

            ordered_cases = sorted(cases, key=lambda case: (case.get("session", case["id"]), case.get("turn", 1)))
            for case in ordered_cases:
                old_record = progress["records"].get(case["id"])

                if old_record is not None:
                    # This question was asked in an earlier run. Only the metrics that
                    # are missing or were stopped by the daily limit need to run again.
                    pending = [
                        name for name in metrics
                        if name not in old_record["metrics"]
                        or old_record["metrics"][name].get("rate_limited")
                        or (args.rescore and old_record["metrics"][name]["score"] is None and not old_record["should_refuse"])
                    ]
                    if not pending:
                        continue
                    record = old_record
                    test_case = LLMTestCase(
                        input=record["question"], actual_output=record["answer"],
                        expected_output=record["expected_answer"], retrieval_context=record["contexts"],
                    )
                else:
                    # A shared session id preserves the two-turn follow-up case.
                    # The session id is also saved, so a follow-up still works on the next day.
                    session_key = case.get("session", case["id"])
                    session_id = progress["sessions"].setdefault(session_key, str(uuid.uuid4()))
                    try:
                        response = await client.post(
                            "/ask", headers={"Authorization": "Bearer " + token},
                            json={"question": case["question"], "session_id": session_id, "retrieval_config": strategy, "include_contexts": True},
                        )
                        response.raise_for_status()
                        output = response.json()
                        warm_output = None
                        if not case.get("session"):
                            warm_response = await client.post(
                                "/ask", headers={"Authorization": "Bearer " + token},
                                json={"question": case["question"], "session_id": str(uuid.uuid4()), "retrieval_config": strategy},
                            )
                            warm_response.raise_for_status()
                            warm_output = warm_response.json()
                    except httpx.HTTPStatusError as error:
                        print(f"Stopped at {case['id']}: the app answered with error {error.response.status_code}.")
                        print("Server said:", error.response.text[:300])
                        print("Most likely the daily Groq limit is over. Your progress is saved. Run again later.")
                        save_progress(progress_path, progress)
                        stop_run = True
                        break

                    test_case = LLMTestCase(
                        input=case["question"], actual_output=output["answer"],
                        expected_output=case["expected_answer"], retrieval_context=output.get("contexts", []),
                    )
                    record = {
                        "id": case["id"], "question": case["question"], "answer": output["answer"],
                        "expected_answer": case["expected_answer"], "refused": output.get("refused", False),
                        "should_refuse": case["should_refuse"], "contexts": output.get("contexts", []),
                        "cold_latency_ms": output["latency_ms"],
                        "warm_latency_ms": warm_output["latency_ms"] if warm_output else None,
                        "cache_hit": warm_output.get("cached", False) if warm_output else False,
                        "metrics": {},
                    }
                    pending = list(metrics)
                    if case["should_refuse"]:
                        # A question that must be refused has no real answer to grade, so the five
                        # DeepEval metrics are skipped for it. It is counted in the refusal accuracy.
                        for name in metrics:
                            record["metrics"][name] = {"score": None, "reason": "Skipped: this question should be refused."}
                        pending = []

                for name in pending:
                    try:
                        metrics[name].measure(test_case)
                        record["metrics"][name] = {"score": metrics[name].score, "reason": metrics[name].reason}
                    except Exception as error:
                        limit_hit = is_rate_limit(error)
                        record["metrics"][name] = {"score": None, "reason": str(error), "rate_limited": limit_hit}
                        if limit_hit:
                            stop_run = True
                            break

                progress["records"][case["id"]] = record
                save_progress(progress_path, progress)
                print(f"{strategy}: {case['id']} saved")
                if stop_run:
                    print("Daily Groq limit reached while scoring. Your progress is saved. Run again later.")
                    break

            records = [progress["records"][case["id"]] for case in ordered_cases if case["id"] in progress["records"]]

            def is_finished(row):
                return all(name in row["metrics"] and not row["metrics"][name].get("rate_limited") for name in metrics)

            def averages(rows):
                result = {}
                for name in metrics:
                    scores = [row["metrics"][name]["score"] for row in rows if name in row["metrics"] and row["metrics"][name]["score"] is not None]
                    result[name] = round(statistics.mean(scores), 4) if scores else None
                return result

            finished_count = sum(1 for row in records if is_finished(row))
            if stop_run or finished_count < len(ordered_cases):
                print(f"Finished {finished_count} of {len(ordered_cases)} questions so far.")
                print("Averages so far (only for information):", averages([row for row in records if is_finished(row)]))
                print("Run the same command again later and it will continue from here.")
                break

            # Everything is finished: build the final numbers from the saved records.
            cold_times = [row["cold_latency_ms"] for row in records]
            warm_times = [row["warm_latency_ms"] for row in records if row["warm_latency_ms"] is not None]
            cold_single_times = [row["cold_latency_ms"] for row in records if row["warm_latency_ms"] is not None]
            warm_hits = sum(int(row["cache_hit"]) for row in records if row["warm_latency_ms"] is not None)
            refusal_correct = sum(int(bool(row["refused"]) == row["should_refuse"]) for row in records)
            refusal_cases_total = sum(1 for row in records if row["should_refuse"])
            refusal_cases_correct = sum(int(bool(row["refused"])) for row in records if row["should_refuse"])

            metric_averages = averages(records)
            summary = {
                "config": strategy, "case_count": len(records), "metric_averages": metric_averages,
                "refusal_accuracy": round(refusal_correct / len(records), 4) if records else None,
                "refusal_correct": refusal_correct, "refusal_total": len(records),
                "expected_refusal_accuracy": round(refusal_cases_correct / refusal_cases_total, 4) if refusal_cases_total else None,
                "expected_refusal_correct": refusal_cases_correct, "expected_refusal_total": refusal_cases_total,
                "cold_latency_ms": {"min": min(cold_times, default=None), "mean": round(statistics.mean(cold_times), 2) if cold_times else None, "p50": percentile(cold_times, 0.50), "p95": percentile(cold_times, 0.95), "max": max(cold_times, default=None)},
                "warm_latency_ms": {"min": min(warm_times, default=None), "mean": round(statistics.mean(warm_times), 2) if warm_times else None, "p50": percentile(warm_times, 0.50), "p95": percentile(warm_times, 0.95), "max": max(warm_times, default=None)},
                "cache_hit_rate": round(warm_hits / len(warm_times), 4) if warm_times else None,
                "warm_speedup": round(statistics.mean(cold_single_times) / statistics.mean(warm_times), 2) if warm_times and statistics.mean(warm_times) else None,
                "records": records,
            }
            output_path = results_folder / f"{strategy}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            lines = [f"# PolicyBot evaluation: {strategy}", "", f"Cases: {len(records)}", "", "## DeepEval metric averages", ""]
            lines.extend(f"- {name}: {score}" for name, score in metric_averages.items())
            lines.extend(["", f"Refusal accuracy: {summary['refusal_accuracy']} ({refusal_correct}/{len(records)})", f"Expected-refusal accuracy: {summary['expected_refusal_accuracy']} ({refusal_cases_correct}/{refusal_cases_total})", "", f"Cold latency (ms): {summary['cold_latency_ms']}", f"Warm latency (ms): {summary['warm_latency_ms']}", f"Cache hit rate: {summary['cache_hit_rate']}", f"Warm speedup: {summary['warm_speedup']}x", ""])
            output_path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
            print(f"Saved {output_path}")




if __name__ == "__main__":
    asyncio.run(main())