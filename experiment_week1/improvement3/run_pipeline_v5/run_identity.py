"""Record source and data identity without exporting environment secrets."""
import hashlib
import json
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_run_identity(package_dir, input_files, configuration):
    root = Path(package_dir)
    source = {path.relative_to(root).as_posix(): sha256_file(path)
              for path in sorted(root.rglob("*.py")) if "tests" not in path.parts and "docs" not in path.parts}
    data = {name: {"path": str(Path(path).resolve()), "sha256": sha256_file(path)}
            for name, path in input_files.items()}
    manifest = {"source_files": source, "input_files": data, "configuration": configuration}
    identity = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest()
    return identity, {"run_identity": identity, **manifest}
