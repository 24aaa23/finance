"""Create the shared knowledge cache using a model draft followed by review.

Accepts run.py input options, including --env-file, --ontology, --kg-data,
--domain-intro and --business-rules. Run with --help to see all options.
"""
import os
from pathlib import Path
import subprocess
import sys


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--knowledge-cache" in arguments or any(arg.startswith("--knowledge-cache=") for arg in arguments):
        raise SystemExit("This script creates a cache; use run.py --knowledge-cache to select an existing cache.")
    environment = os.environ.copy()
    # A previously selected cache must not bypass creation for current inputs.
    environment["KNOWLEDGE_CACHE_FILE"] = ""
    command = [sys.executable, "-u", "-B", str(Path(__file__).with_name("run.py")),
               "--prepare-knowledge", "--knowledge-mode", "simple", *arguments]
    return subprocess.run(command, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
