"""Wall-clock accounting without storing prompts, answers or credentials."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
import csv
import json
import math
import os
from pathlib import Path
import time
from types import SimpleNamespace
from uuid import uuid4


REPORT_METRIC_COLUMNS = ["Timing Run ID", "Target Model", "Generation Input Tokens",
                         "Generation Output Tokens", "Cached Input Tokens", "Generation Latency Seconds",
                         "Model Calls", "Failed Model Calls", "Calls Missing Token Usage"]


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
        self.run_id = uuid4().hex
        self.events_path = None
        self.output_summary_path = None

    def enable_output_records(self, folder, **metadata):
        """One append-only event stream per process, including interrupted attempts."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        self.metadata.update(metadata)
        self.events_path = folder / f"{self.run_id}.events.jsonl"
        self.output_summary_path = folder / f"{self.run_id}.timing.json"
        self._event("run_started", started_at=self.started_at, metadata=dict(self.metadata))

    def _event(self, event, **record):
        if self.events_path is None:
            return
        try:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"event": event, "run_id": self.run_id, **record}) + "\n")
        except OSError:
            # Measurement failures must not replace a model response/error.
            self.metadata["event_write_failed"] = True

    def report_metrics(self, first_call):
        """Metrics for the current question attempt, excluding startup compilation."""
        calls = self.llm_calls[first_call:]
        def complete_sum(key):
            return sum(c[key] for c in calls) if all(c.get(key) is not None for c in calls) else None
        models = sorted({c["model"] for c in calls if c.get("model")})
        return {"Timing Run ID": self.run_id,
                "Target Model": ", ".join(models) or self.metadata.get("model", ""),
                "Generation Input Tokens": complete_sum("prompt_tokens"),
                "Generation Output Tokens": complete_sum("completion_tokens"),
                "Cached Input Tokens": complete_sum("cached_prompt_tokens"),
                "Generation Latency Seconds": sum(c["seconds"] for c in calls),
                "Model Calls": len(calls),
                "Failed Model Calls": sum(c["status"] == "error" for c in calls),
                "Calls Missing Token Usage": sum(c.get("prompt_tokens") is None or c.get("completion_tokens") is None for c in calls)}

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
        record = {"query_id": str(row_id), "attempt_id": uuid4().hex}
        self._event("question_started", **record)
        try:
            yield record
        finally:
            record["cycle_seconds"] = self.clock() - started
            calls = self.llm_calls[first_call:]
            record["llm_seconds"] = sum(call["seconds"] for call in calls)
            record["llm_calls"] = len(calls)
            self.questions.append(record)
            self.query_id.reset(token)
            self._event("question_finished", **record)

    def client(self, client):
        def create(**request):
            started = self.clock()
            record = {"stage": self.stage_name.get(), "query_id": self.query_id.get(),
                      "call_id": uuid4().hex, "model": request.get("model"),
                      "prompt_characters": sum(len(m.get("content") or "")
                                               for m in request.get("messages", []))}
            self._event("call_started", **record)
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
                self._event("call_finished", **record)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    def snapshot(self, status):
        return {"run_id": self.run_id, "started_at": self.started_at, "status": status,
                "wall_clock_seconds": self.elapsed(), "startup_seconds": self.startup_seconds,
                "current_run_query_seconds": sum(q.get("processing_seconds", 0) for q in self.questions),
                "current_run_cycle_seconds": sum(q["cycle_seconds"] for q in self.questions),
                "llm_seconds": sum(c["seconds"] for c in self.llm_calls),
                "metadata": self.metadata, "questions": self.questions,
                "stages": self.stages, "llm_calls": self.llm_calls,
                "timing_scope": "CLI entry through result/log finalization; excludes interpreter bootstrap and this timing summary write",
                "stage_accounting": "Stage durations may nest; do not add them to wall-clock time.",
                "cached_tokens_note": "null means the endpoint did not report cache usage; it does not mean zero",
                "usage_note": "SDK internal retry usage may be unavailable. Call duration includes SDK retries/backoff. "
                              "Token usage is provider-reported, not a verified bill. Event and summary files describe the same calls; do not add both."}

    def save(self, path, status):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.snapshot(status), indent=2), encoding="utf-8")
        os.replace(temporary, path)
        if self.output_summary_path is not None and path.resolve() != self.output_summary_path.resolve():
            destination = self.output_summary_path
            temporary = destination.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.snapshot(status), indent=2), encoding="utf-8")
            os.replace(temporary, destination)
        if self.output_summary_path is not None:
            self._save_csv_records()

    def _save_csv_records(self):
        """Export safe accounting fields for the experiment's metrics reader."""
        folder = self.output_summary_path.parent
        call_fields = ["run_id", "call_id", "stage", "query_id", "model", "status", "error_type",
                       "prompt_tokens", "completion_tokens", "total_tokens", "cached_prompt_tokens", "seconds"]
        question_fields = ["run_id", "query_id", "attempt_id", "processing_seconds", "cycle_seconds", "llm_seconds", "llm_calls", "status"]
        def write(path, rows, fields):
            temporary = path.with_suffix(path.suffix + ".tmp")
            with temporary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            os.replace(temporary, path)
        write(folder / f"{self.run_id}.calls.csv", [{"run_id": self.run_id, **row} for row in self.llm_calls], call_fields)
        write(folder / f"{self.run_id}.questions.csv", [{"run_id": self.run_id, **row} for row in self.questions], question_fields)
        # Each canonical output folder has one report writer. Per-run snapshots
        # replace themselves, so repeat saves/resume do not double-count calls.
        calls = {}
        for source in sorted(folder.glob("*.calls.csv")):
            with source.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    calls[row["call_id"]] = row
        write(folder.parent / "model_calls.csv", list(calls.values()), call_fields)

    def summary(self):
        totals = {}
        for call in self.llm_calls:
            totals[call["stage"]] = totals.get(call["stage"], 0) + call["seconds"]
        slowest = ", ".join(f"{name}={seconds:.2f}s" for name, seconds in
                            sorted(totals.items(), key=lambda item: item[1], reverse=True)[:4])
        return (f"[TIME] Startup-to-finish: {self.elapsed():.2f}s; "
                f"model requests: {sum(totals.values()):.2f}s ({len(self.llm_calls)} calls)."
                + (f" Slowest model stages: {slowest}" if slowest else ""))
