from __future__ import annotations

from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Iterable


def temporary_cleanup_plan(storage_root:Path,active_storage_keys:Iterable[str],retention_days:int)->list[Path]:
    root=storage_root.resolve();queue=(root/"_queue").resolve();active=set(active_storage_keys);threshold=datetime.now(timezone.utc)-timedelta(days=retention_days);planned=[]
    if not queue.is_dir() or root not in queue.parents:return planned
    for path in queue.rglob("*"):
        if not path.is_file():continue
        resolved=path.resolve();relative=resolved.relative_to(root).as_posix()
        if root not in resolved.parents or relative in active:continue
        modified=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc)
        if modified<threshold:planned.append(resolved)
    return planned


def apply_temporary_cleanup(storage_root:Path,planned:Iterable[Path])->int:
    root=storage_root.resolve();queue=(root/"_queue").resolve();removed=0
    for path in planned:
        resolved=path.resolve()
        if queue not in resolved.parents:raise ValueError("retention cleanup may delete only queued temporary sources")
        resolved.unlink(missing_ok=True);removed+=1
    return removed


def retention_policy(settings)->dict:
    return {"source_documents":{"days":settings.source_retention_days,"automatic_delete":False},
        "exports":{"days":settings.export_retention_days,"automatic_delete":False},
        "ai_temporary":{"hours":settings.ai_temp_retention_hours,"automatic_delete":True},
        "queued_temporary":{"days":settings.temp_retention_days,"automatic_delete":True},
        "accounting_audit":{"automatic_delete":False},"logs":{"rotation_bytes":settings.log_max_bytes,"backup_count":settings.log_backup_count}}
