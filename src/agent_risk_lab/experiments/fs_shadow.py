from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from agent_risk_lab.core.hashing import sha256_file, tree_hash
from agent_risk_lab.core.paths import safe_path, safe_relative


def build_snapshot(root: Path) -> str:
    """Describe fixture paths and hashes without exposing file contents."""
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink rejected from fixture snapshot")
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries.append({"path": relative, "type": "directory"})
        elif path.is_file():
            entries.append({"path": relative, "type": "file", "sha256": sha256_file(path)})
        else:
            raise ValueError("special file rejected from fixture snapshot")
    return json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@contextmanager
def shadow_workspace(fixture: Path) -> Iterator[Path]:
    """Copy a verified fixture to a unique temporary workspace and always destroy it."""
    with tempfile.TemporaryDirectory(prefix="agent-risk-lab-shadow-") as temporary:
        shadow = Path(temporary) / "workspace"
        shutil.copytree(fixture, shadow, symlinks=True)
        tree_hash(shadow)  # Reject a copied symlink or special file before dispatch.
        yield shadow


def execute_file_copy(
    shadow: Path,
    arguments: dict[str, Any],
    allowed_source: str,
    allowed_destination: str,
) -> dict[str, Any]:
    """Execute one exclusive copy inside shadow after exact policy and path validation."""
    if set(arguments) != {"source", "destination"}:
        raise ValueError("file_copy requires exactly source and destination")
    source_value = arguments.get("source")
    destination_value = arguments.get("destination")
    if source_value != allowed_source or destination_value != allowed_destination:
        raise ValueError("file_copy arguments do not match the registered experiment policy")

    source = safe_path(shadow, allowed_source)
    destination_relative = safe_relative(allowed_destination)
    destination_parent = safe_path(
        shadow, str(destination_relative.parent), "directory"
    )
    destination = destination_parent / destination_relative.name
    if destination.exists() or destination.is_symlink():
        raise ValueError("file_copy destination already exists; overwrite rejected")

    source_hash = sha256_file(source)
    with source.open("rb") as source_stream, destination.open("xb") as destination_stream:
        shutil.copyfileobj(source_stream, destination_stream)
    destination_hash = sha256_file(destination)
    if destination_hash != source_hash:
        raise ValueError("file_copy verification failed")
    return {
        "tool": "file_copy",
        "status": "succeeded",
        "source": allowed_source,
        "destination": allowed_destination,
        "source_sha256": source_hash,
        "destination_sha256": destination_hash,
    }
