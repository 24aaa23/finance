"""Run V4 directly without changing the existing V3 launcher."""
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from run_pipeline_v4.main import main
    main()
