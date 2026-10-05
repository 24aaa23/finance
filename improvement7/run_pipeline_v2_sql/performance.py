"""Wall-clock accounting without storing prompts, answers or credentials."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
import json
import math
import os
from pathlib import Path
import time
from types import SimpleNamespace


def query_delay(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Query delay must be a finite non-negative number.")
    return seconds


class RunTiming:
    def __init__(self, started=None, clock=None):
        self.clock = clock or time.perf_counter
        self.started = self.clock() if started is None else started
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.stage_name = ContextVar("timing_stage", default="unattributed")
        self.query_id = ContextVar("timing_query", default=None)
        self.stages = []
        self.llm_calls = []
        self.questions = []
        self.metadata = {}
        self.startup_seconds = None

    def elapsed(self):
        return self.clock() - self.started

    @contextmanager
    def stage(self, name):
        started = self.clock()
        token = self.stage_name.set(name)
        try:
            yield
        finally:
            self.stages.append({"stage": name, "query_id": self.query_id.get(),
                                "seconds": self.clock() - started})
            self.stage_name.reset(token)

    def operator(self, name, function):
        def invoke(inputs):
            with self.stage(name):
                return function(inputs)
        return invoke

    def ready(self):
        self.startup_seconds = self.elapsed()

    @contextmanager
    def question(self, row_id):
        started = self.clock()
        first_call = len(self.llm_calls)
        token = self.query_id.set(str(row_id))
        record = {"query_id": str(row_id)}
        try:
            yield record
        finally:
            record["cycle_seconds"] = self.clock() - started
            calls = self.llm_calls[first_call:]
            record["llm_seconds"] = sum(call["seconds"] for call in calls)
            record["llm_calls"] = len(calls)
            self.questions.append(record)
            self.query_id.reset(token)

    def client(self, client):
        def create(**request):
            started = self.clock()
            record = {"stage": self.stage_name.get(), "query_id": self.query_id.get(),
                      "prompt_characters": sum(len(m.get("content") or "")
                                               for m in request.get("messages", []))}
            try:
                response = client.chat.completions.create(**request)
                record["status"] = "success"
                usage = getattr(response, "usage", None)
                if hasattr(usage, "model_dump"):
                    usage = usage.model_dump()
                elif usage is not None and not isinstance(usage, dict):
                    usage = vars(usage)
                usage = usage or {}
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    record[key] = usage.get(key)
                details = usage.get("prompt_tokens_details") or {}
                record["cached_prompt_tokens"] = details.get("cached_tokens") if isinstance(details, dict) else None
                return response
            except BaseException as exc:
                record.update(status="error", error_type=type(exc).__name__)
                raise
            finally:
                # Includes SDK retries/backoff inside create(), even on failure.
                record["seconds"] = self.clock() - started
                self.llm_calls.append(record)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    def snapshot(self, status):
        return {"started_at": self.started_at, "status": status,
                "wall_clock_seconds": self.elapsed(), "startup_seconds": self.startup_seconds,
                "current_run_query_seconds": sum(q.get("processing_seconds", 0) for q in self.questions),
                "current_run_cycle_seconds": sum(q["cycle_seconds"] for q in self.questions),
                "llm_seconds": sum(c["seconds"] for c in self.llm_calls),
                "metadata": self.metadata, "questions": self.questions,
                "stages": self.stages, "llm_calls": self.llm_calls,
                "timing_scope": "CLI entry through result/log finalization; excludes interpreter bootstrap and this timing summary write",
                "stage_accounting": "Stage durations may nest; do not add them to wall-clock time.",
                "cached_tokens_note": "null means the endpoint did not report cache usage; it does not mean zero"}

    def save(self, path, status):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.snapshot(status), indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def summary(self):
        totals = {}
        for call in self.llm_calls:
            totals[call["stage"]] = totals.get(call["stage"], 0) + call["seconds"]
        slowest = ", ".join(f"{name}={seconds:.2f}s" for name, seconds in
                            sorted(totals.items(), key=lambda item: item[1], reverse=True)[:4])
        return (f"[TIME] Startup-to-finish: {self.elapsed():.2f}s; "
                f"model requests: {sum(totals.values()):.2f}s ({len(self.llm_calls)} calls)."
                + (f" Slowest model stages: {slowest}" if slowest else ""))
