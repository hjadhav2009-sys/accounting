from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg

from tests.v2.test_phase3 import SUJAL_TEXT,pdf_with_text
from v2.backend.app.infrastructure.postgres_migrations import apply_migrations
from v2.backend.app.security.bootstrap import bootstrap_admin


def main()->int:
    url=os.environ["POSTGRES_TEST_DATABASE_URL"];organization=f"Browser E2E {uuid4()}";email=f"browser-{uuid4()}@example.invalid";password="Browser-E2E-Secure!7"
    connection=psycopg.connect(url);apply_migrations(connection);result=bootstrap_admin(connection,organization,"Browser Test Company",email,"Browser Owner",password);connection.close()
    upload=Path(os.environ.get("E2E_UPLOAD_PATH",Path.cwd()/".runtime"/"e2e-upload.pdf"));upload.parent.mkdir(parents=True,exist_ok=True);upload.write_bytes(pdf_with_text(SUJAL_TEXT.replace("2600000122",f"26{uuid4().hex[:8].upper()}")))
    print(json.dumps({"organization":organization,"email":email,"password":password,"company_id":result["company_id"],"upload":str(upload.resolve())}));return 0


if __name__=="__main__":raise SystemExit(main())
