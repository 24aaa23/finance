"""Live compilation progress and local diagnostic files for rejected responses."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import threading
import time


class KnowledgeProgress:
    def __init__(self, cache_dir, interval=20):
        self.interval = interval
        self.path = Path(cache_dir).parent / "logs" / f"knowledge_{time.time_ns()}_{os.getpid()}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def emit(self, event, message, **details):
        record = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **details}
        with self.lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            print(f"[KNOWLEDGE] {message}", file=sys.__stdout__, flush=True)

    def save_rejection(self, label, attempt, content, reason, finish_reason):
        """Save only the returned answer, not request prompts or client configuration."""
        name = re.sub(r"[^a-zA-Z0-9_-]+", "_", label)
        path = self.path.with_name(f"{self.path.stem}_{name}_attempt_{attempt}.rejected.json")
        payload = {"label": label, "attempt": attempt, "finish_reason": finish_reason,
                   "error": reason, "content": content}
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            self.emit("diagnostic_write_failed", "Could not save rejected response; see validation error above.")
            return
        self.emit("rejected_response_saved", f"Rejected response saved for inspection: {path}", path=str(path))

    @contextmanager
    def waiting(self, attempt, label="Domain"):
        started = time.monotonic()
        stopped = threading.Event()

        def heartbeat():
            while not stopped.wait(self.interval):
                elapsed = round(time.monotonic() - started, 1)
                self.emit("waiting", f"{label}, attempt {attempt}/3: waiting for model, {elapsed}s elapsed. "
                          "SDK retries may be included; server progress is unknown.",
                          label=label, attempt=attempt, elapsed_seconds=elapsed)

        thread = threading.Thread(target=heartbeat, daemon=True, name="knowledge-progress")
        thread.start()
        try:
            yield
        except BaseException as exc:
            stopped.set()
            thread.join()
            self.emit("request_failed", f"Attempt {attempt}/3 stopped: {type(exc).__name__}.",
                      attempt=attempt, error_type=type(exc).__name__)
            raise
        finally:
            stopped.set()
            thread.join()


def parse_complete_pack(content):
    """Unwrap a full JSON object without repairing or extracting nested fragments.

    The first JSON opening delimiter is authoritative: a broken outer object is
    never skipped in favor of an inner rule/citation. Only surrounding prose,
    complete leading reasoning blocks, and one Markdown fence are tolerated.
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Expected complete JSON object, but response content is empty or not text.")
    text = content.lstrip("\ufeff").strip()
    # Do not alter reasoning-like strings inside actual rule text or citations.
    while re.match(r"<(think|thought|reasoning)>", text, re.I):
        block = re.match(r"<(think|thought|reasoning)>.*?</\1>\s*", text, re.I | re.S)
        if block is None:
            raise ValueError("Expected complete JSON after reasoning; reasoning block is not closed.")
        text = text[block.end():].lstrip()
    # Locate one outer JSON object, optionally preceded by a short prose/fence
    # wrapper. Never search again after this delimiter if decoding fails.
    openings = [position for marker in ("{", "[") if (position := text.find(marker)) >= 0]
    if not openings:
        raise ValueError("Expected complete JSON object; no opening JSON delimiter in response.")
    start = min(openings)
    prefix = text[:start].strip()
    fenced = "```" in prefix
    if fenced and not re.fullmatch(r"[^`]*```(?:json)?\s*", prefix, re.I):
        raise ValueError("Expected one complete JSON object; unsupported or multiple Markdown fences.")
    try:
        value, end = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Response is not valid complete JSON: {exc.msg} at line {exc.lineno}, "
                         f"column {exc.colno} (character {exc.pos}). Use double-quoted keys/strings; "
                         "escape quotes, backslashes and newlines inside strings. Return the entire object.") from exc
    if not isinstance(value, dict):
        raise ValueError("Expected a complete JSON object, not an array or scalar.")
    suffix = text[end:].strip()
    if fenced:
        if not suffix.startswith("```"):
            raise ValueError("Expected complete JSON with a closed Markdown fence.")
        suffix = suffix[3:].strip()
    if any(marker in suffix for marker in ("{", "[", "}", "]", "```")):
        raise ValueError("Ambiguous response: extra JSON or unmatched delimiters after the complete object.")
    return value
