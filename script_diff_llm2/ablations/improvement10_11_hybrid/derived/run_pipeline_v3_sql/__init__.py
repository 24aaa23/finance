"""Pipeline package; configure numerical libraries before importing pandas."""
import os

# Eight independent terminals do not need eight additional BLAS thread pools.
# On this machine pandas used ~401 MB with defaults versus ~48 MB with one
# numerical thread. This does not restrict independent pipeline processes.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
              "NUMEXPR_NUM_THREADS", "NUMEXPR_MAX_THREADS", "BLIS_NUM_THREADS"):
    os.environ[_name] = "1"

