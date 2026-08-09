from __future__ import annotations

import json
import logging
import re
from datetime import datetime,timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


SAFE_FIELDS=("event","error_code","job_id","batch_id","tenant","company","stage","status","duration_ms")


class SafeJsonFormatter(logging.Formatter):
    def format(self,record:logging.LogRecord)->str:
        message=record.getMessage()[:1000]
        message=re.sub(r"(?i)(password|token|secret|authorization)\s*[:=]\s*\S+",r"\1=[REDACTED]",message)
        message=re.sub(r"(?i)(postgres(?:ql)?://[^:\s/]+):[^@\s]+@",r"\1:[REDACTED]@",message)
        payload={"timestamp":datetime.now(timezone.utc).isoformat(),"level":record.levelname,
            "logger":record.name,"message":message}
        for field in SAFE_FIELDS:
            value=getattr(record,field,None)
            if value not in (None,""):payload[field]=str(value)[:200]
        if record.exc_info:payload["exception_type"]=record.exc_info[0].__name__
        return json.dumps(payload,separators=(",",":"),ensure_ascii=True)


def configure_logging(repository_root:Path,max_bytes:int,backup_count:int)->Path:
    directory=repository_root/".runtime"/"logs";directory.mkdir(parents=True,exist_ok=True);path=directory/"backend.jsonl"
    root=logging.getLogger();existing=next((handler for handler in root.handlers if getattr(handler,"_bap_structured",False)),None)
    if not existing:
        handler=RotatingFileHandler(path,maxBytes=max_bytes,backupCount=backup_count,encoding="utf-8",delay=True);handler.setFormatter(SafeJsonFormatter());handler._bap_structured=True;root.addHandler(handler);root.setLevel(logging.INFO)
    return path
