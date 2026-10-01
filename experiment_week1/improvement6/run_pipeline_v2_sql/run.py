"""Run the SQLite pipeline without changing the existing KG launcher."""
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from run_pipeline_v2_sql.runtime_guard import launch as main
    main()
