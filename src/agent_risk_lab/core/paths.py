from pathlib import Path, PurePosixPath, PureWindowsPath
import os, stat
MAX_TEXT=1024*1024; MAX_PDF=10*1024*1024
def safe_relative(value:str)->PurePosixPath:
    p=PurePosixPath(value); windows=PureWindowsPath(value)
    if not value or "\0" in value or "\\" in value or p.is_absolute() or windows.is_absolute() or windows.drive or ".." in p.parts: raise ValueError("unsafe relative path")
    return p
def safe_path(base:Path,value:str,kind:str="file")->Path:
    p=base
    for part in safe_relative(value).parts:
        p=p/part; st=p.lstat()
        if stat.S_ISLNK(st.st_mode): raise ValueError("symlink rejected")
    if kind=="file" and not p.is_file(): raise ValueError("regular file required")
    if kind=="directory" and not p.is_dir(): raise ValueError("directory required")
    return p
def read_prompt(path:Path)->tuple[bytes,str]:
    if path.is_symlink() or not path.is_file(): raise ValueError("regular non-symlink prompt required")
    data=path.read_bytes(); limit=MAX_PDF if path.suffix.lower()==".pdf" else MAX_TEXT
    if len(data)>limit: raise ValueError("prompt is oversized")
    if path.suffix.lower()==".pdf":
        if not data.startswith(b"%PDF-"): raise ValueError("invalid PDF")
        return data,"application/pdf"
    try: data.decode("utf-8")
    except UnicodeDecodeError as e: raise ValueError("prompt must be UTF-8") from e
    if data.startswith(b"\xef\xbb\xbf"): raise ValueError("UTF-8 BOM rejected")
    return data,"text/plain"
