"""Launch with python -m run_pipeline_v3 from the improvement5 directory."""
from .run import configure_run

if __name__ == "__main__" and configure_run():
    from .main import main
    main()
