"""Compatibility entrypoint for improvement3 pipeline V4."""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from run_pipeline_v4.main import main


if __name__ == "__main__":
    main()
