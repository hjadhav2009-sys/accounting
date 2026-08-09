from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from .backup import create_backup,restore_backup,verify_backup


def main()->int:
    parser=argparse.ArgumentParser(description="Create, verify, or restore an encrypted Business Automation V2 backup.")
    commands=parser.add_subparsers(dest="command",required=True)
    create=commands.add_parser("create");create.add_argument("destination",type=Path);create.add_argument("--storage-root",type=Path,required=True);create.add_argument("--metadata-only",action="store_true")
    verify=commands.add_parser("verify");verify.add_argument("source",type=Path)
    restore=commands.add_parser("restore");restore.add_argument("source",type=Path);restore.add_argument("--target-database-url",required=True);restore.add_argument("--storage-root",type=Path,required=True)
    args=parser.parse_args();password=getpass.getpass("Backup password: ")
    if args.command=="create":
        database_url=os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
        if not database_url:parser.error("POSTGRES_URL or DATABASE_URL must be configured")
        confirmation=getpass.getpass("Confirm backup password: ")
        if password!=confirmation:parser.error("passwords do not match")
        result=create_backup(database_url,args.storage_root,args.destination,password,include_sources=not args.metadata_only)
    elif args.command=="verify":result=verify_backup(args.source,password)
    else:result=restore_backup(args.source,password,args.target_database_url,args.storage_root)
    print(result);return 0


if __name__=="__main__":raise SystemExit(main())
