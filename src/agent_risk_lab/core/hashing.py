import hashlib, json
from pathlib import Path
from typing import Any

def sha256_bytes(value: bytes) -> str: return hashlib.sha256(value).hexdigest()
def sha256_file(path: Path) -> str: return sha256_bytes(path.read_bytes())
def canonical_hash(value: Any) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())

def tree_hash(root: Path) -> str:
    rows=[]
    for path in sorted(root.rglob("*")):
        if path.is_symlink(): raise ValueError("symlink rejected")
        rel=path.relative_to(root).as_posix()
        if path.is_file(): rows.append([rel, sha256_file(path)])
        elif path.is_dir(): rows.append([rel, None])
        else: raise ValueError("special file rejected")
    return canonical_hash(rows)
