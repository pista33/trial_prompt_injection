from __future__ import annotations
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
def write_log(directory:Path,record:dict)->Path:
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/f"experiment_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex}.jsonl"
    with path.open("x",encoding="utf-8",newline="\n") as out: out.write(json.dumps(record,ensure_ascii=False,sort_keys=True)+"\n")
    return path
