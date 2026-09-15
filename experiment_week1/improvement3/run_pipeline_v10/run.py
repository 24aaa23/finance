"""Run V10 directly from any working directory."""
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from run_pipeline_v10.main import main
    main()
