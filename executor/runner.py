"""Container entrypoint for a user-provided experiment."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    entrypoint = config.get("entrypoint", "train.py")
    entrypoint_path = Path("/workspace/code") / entrypoint
    if not entrypoint_path.is_file() or entrypoint_path.parent != Path("/workspace/code"):
        raise SystemExit("entrypoint must be a file at the code directory root")
    os.environ["EXPERIMENT_CONFIG"] = json.dumps(config)
    os.chdir("/workspace/output")
    sys.path.insert(0, str(entrypoint_path.parent))
    runpy.run_path(str(entrypoint_path), run_name="__main__")


if __name__ == "__main__":
    main()
