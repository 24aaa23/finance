"""Run V6 directly without changing the older pipeline launchers."""
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from run_pipeline_v6.main import main
    main()
