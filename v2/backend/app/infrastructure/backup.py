from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from typing import Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from psycopg.conninfo import conninfo_to_dict,make_conninfo


MAGIC=b"BAPBACKUP1\0"


def _sha256(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()


def _tool(name:str,configured:str="")->str:
    candidates=[configured,shutil.which(name),str(Path("C:/Program Files/PostgreSQL/18/bin")/(name+".exe"))]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():return str(Path(candidate).resolve())
    raise RuntimeError(f"{name} was not found; configure the PostgreSQL 18 bin directory")


def _safe_connection_environment(url:str)->tuple[str,dict[str,str]]:
    values=conninfo_to_dict(url);password=values.pop("password",None) or os.getenv("POSTGRES_PASSWORD");environment=os.environ.copy()
    if password:environment["PGPASSWORD"]=password
    return make_conninfo(**values),environment


def _key(password:str,salt:bytes)->bytes:
    if len(password)<12:raise ValueError("backup password must contain at least 12 characters")
    return Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode("utf-8"))


def _encrypt(source:Path,destination:Path,password:str)->None:
    salt=os.urandom(16);nonce=os.urandom(12);ciphertext=AESGCM(_key(password,salt)).encrypt(nonce,source.read_bytes(),MAGIC)
    temporary=destination.with_suffix(destination.suffix+".tmp")
    temporary.write_bytes(MAGIC+salt+nonce+ciphertext);os.replace(temporary,destination)


def _decrypt(source:Path,destination:Path,password:str)->None:
    payload=source.read_bytes()
    if not payload.startswith(MAGIC):raise ValueError("not a Business Automation encrypted backup")
    offset=len(MAGIC);salt=payload[offset:offset+16];nonce=payload[offset+16:offset+28]
    destination.write_bytes(AESGCM(_key(password,salt)).decrypt(nonce,payload[offset+28:],MAGIC))


def create_backup(database_url:str,storage_root:Path,destination:Path,password:str,*,
                  include_sources:bool=True,runner:Callable[...,subprocess.CompletedProcess]=subprocess.run)->dict:
    destination=destination.resolve();destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bap-backup-") as temporary_directory:
        staging=Path(temporary_directory);dump=staging/"postgres.dump";archive=staging/"bundle.zip"
        safe_url,environment=_safe_connection_environment(database_url)
        runner([_tool("pg_dump"),"--format=custom","--no-owner","--no-privileges","--file",str(dump),safe_url],
               check=True,capture_output=True,env=environment)
        files={"postgres.dump":_sha256(dump)};source_count=0
        with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
            bundle.write(dump,"postgres.dump")
            root=storage_root.resolve()
            if include_sources and root.is_dir():
                for path in root.rglob("*"):
                    resolved=path.resolve()
                    if path.is_file() and (resolved==root or root in resolved.parents):
                        relative=Path("sources")/resolved.relative_to(root);bundle.write(resolved,relative.as_posix())
                        files[relative.as_posix()]=_sha256(resolved);source_count+=1
            manifest={"format":1,"created_at":datetime.now(timezone.utc).isoformat(),"database":"PostgreSQL",
                      "encrypted":True,"source_count":source_count,"files":files}
            bundle.writestr("manifest.json",json.dumps(manifest,sort_keys=True,indent=2))
        _encrypt(archive,destination,password)
    return {"path":str(destination),"sha256":_sha256(destination),"source_count":source_count,"encrypted":True}


def verify_backup(source:Path,password:str)->dict:
    with tempfile.TemporaryDirectory(prefix="bap-verify-") as directory:
        archive=Path(directory)/"bundle.zip";_decrypt(source.resolve(),archive,password)
        with zipfile.ZipFile(archive) as bundle:
            manifest=json.loads(bundle.read("manifest.json"))
            for name,expected in manifest["files"].items():
                digest=hashlib.sha256(bundle.read(name)).hexdigest()
                if digest!=expected:raise ValueError(f"backup integrity check failed for {name}")
        return manifest


def restore_backup(source:Path,password:str,target_database_url:str,restore_storage_root:Path,*,
                   runner:Callable[...,subprocess.CompletedProcess]=subprocess.run)->dict:
    target=conninfo_to_dict(target_database_url);database=target.get("dbname","")
    if not database.startswith("phase6_restore_"):raise ValueError("restore target must be an isolated phase6_restore_* database")
    import psycopg
    connection=psycopg.connect(target_database_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.schema_migrations')")
            if cursor.fetchone()[0] is not None:raise ValueError("restore target is not empty")
    finally:connection.close()
    with tempfile.TemporaryDirectory(prefix="bap-restore-") as directory:
        archive=Path(directory)/"bundle.zip";_decrypt(source.resolve(),archive,password)
        with zipfile.ZipFile(archive) as bundle:
            manifest=json.loads(bundle.read("manifest.json"))
            for name,expected in manifest["files"].items():
                if hashlib.sha256(bundle.read(name)).hexdigest()!=expected:raise ValueError(f"backup integrity check failed for {name}")
            bundle.extract("postgres.dump",directory)
            restore_storage_root=restore_storage_root.resolve();restore_storage_root.mkdir(parents=True,exist_ok=True)
            for name in manifest["files"]:
                if name.startswith("sources/"):
                    relative=Path(name).relative_to("sources")
                    if ".." in relative.parts:raise ValueError("unsafe backup storage path")
                    destination=(restore_storage_root/relative).resolve()
                    if restore_storage_root not in destination.parents:raise ValueError("unsafe restore destination")
                    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(bundle.read(name))
        safe_url,environment=_safe_connection_environment(target_database_url)
        runner([_tool("pg_restore"),"--no-owner","--no-privileges","--exit-on-error","--dbname",safe_url,str(Path(directory)/"postgres.dump")],
               check=True,capture_output=True,env=environment)
    return {"restored":True,"source_count":manifest["source_count"],"database":database}
