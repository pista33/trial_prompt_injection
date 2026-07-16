import copy
from .hashing import canonical_hash
NAMES=("move_file","rename_file","copy_file","delete_file","write_file","create_directory","send_file","request_confirmation","refuse_operation")
def tool_declarations():
    return [{"type":"function","name":n,"description":"Observation only; never executed.","parameters":{"type":"object","properties":{},"additionalProperties":True}} for n in NAMES]
def tool_schema_sha256(): return canonical_hash(tool_declarations())
