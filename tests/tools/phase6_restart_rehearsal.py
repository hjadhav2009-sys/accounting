from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import psycopg
import requests

from tests.v2.test_phase3 import SUJAL_TEXT
from v2.backend.app.infrastructure.postgres_migrations import apply_migrations


ROOT=Path(__file__).resolve().parents[2];PORT=8010;BASE=f"http://127.0.0.1:{PORT}"


def multi_page_pdf(invoice:str,pages:int=10)->bytes:
    import pymupdf
    text=SUJAL_TEXT.replace("2600000122",invoice);document=pymupdf.open()
    for _ in range(pages):
        page=document.new_page(width=595,height=842);y=36
        for line in text.splitlines():page.insert_text((36,y),line,fontsize=9);y+=13
    content=document.tobytes();document.close();return content


def wait_health(timeout:float=20)->None:
    deadline=time.time()+timeout
    while time.time()<deadline:
        try:
            if requests.get(BASE+"/health",timeout=.5).status_code==200:return
        except requests.RequestException:pass
        time.sleep(.1)
    raise RuntimeError("isolated backend did not become healthy")


def start_backend(environment:dict[str,str],log):
    process=subprocess.Popen([sys.executable,"-m","uvicorn","v2.backend.app.main:app","--host","127.0.0.1","--port",str(PORT),"--log-level","warning"],cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT)
    wait_health();return process


def stop_owned(process:subprocess.Popen)->None:
    if process.poll() is not None:return
    process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def batch_state(url:str,organization,company,batch):
    connection=psycopg.connect(url)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(organization),));cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company),))
            cursor.execute("SELECT status,count(*) FROM durable_document_jobs WHERE batch_id=%s GROUP BY status",(batch,));jobs=dict(cursor.fetchall())
            cursor.execute("SELECT count(*),count(DISTINCT id),count(DISTINCT storage_key) FROM documents WHERE batch_id=%s",(batch,));documents=cursor.fetchone()
            cursor.execute("SELECT count(*) FROM ai_jobs WHERE document_id IN(SELECT id FROM documents WHERE batch_id=%s)",(batch,));ai=cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM document_exports WHERE document_id IN(SELECT id FROM documents WHERE batch_id=%s)",(batch,));exports=cursor.fetchone()[0]
            return jobs,documents,ai,exports
    finally:connection.close()


def main()->int:
    url=os.environ.get("POSTGRES_TEST_DATABASE_URL","")
    if not url:raise RuntimeError("POSTGRES_TEST_DATABASE_URL is required")
    organization,company,user=uuid4(),uuid4(),uuid4();connection=psycopg.connect(url);apply_migrations(connection)
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(organization,f"Restart Rehearsal {organization}"));cursor.execute("SELECT set_config('app.organization_id',%s,true)",(str(organization),));cursor.execute("SELECT set_config('app.company_id',%s,true)",(str(company),));cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Restart Rehearsal','Restart Rehearsal')",(company,organization));cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Restart Operator','ACTIVE')",(user,organization,f"{user}@example.invalid"))
    connection.commit();connection.close();headers={"X-Organization-ID":str(organization),"X-Company-ID":str(company),"X-User-ID":str(user),"X-Roles":"OPERATOR"}
    with tempfile.TemporaryDirectory(prefix="phase6-restart-") as directory:
        temp=Path(directory);environment=os.environ.copy();environment.update({"POSTGRES_URL":url,"DATABASE_URL":url,"STORAGE_ROOT":str(temp/"storage"),"DURABLE_WORKER_ENABLED":"true","DURABLE_WORKER_POLL_SECONDS":"0.1","DURABLE_STALE_SECONDS":"1","PRODUCTION_AUTH_ENABLED":"false"})
        log=(temp/"backend.log").open("w",encoding="utf-8");process=None
        try:
            process=start_backend(environment,log);files=[("files",(f"restart-{index}.pdf",multi_page_pdf(f"26000{index:05d}"),"application/pdf")) for index in range(10)]
            response=requests.post(BASE+"/api/v2/documents/batch",headers=headers,files=files,timeout=30);response.raise_for_status();batch=response.json()["batch_id"]
            deadline=time.time()+15;saw_running=False
            while time.time()<deadline:
                jobs,_,_,_=batch_state(url,organization,company,batch)
                if jobs.get("RUNNING",0):saw_running=True;break
                if jobs.get("COMPLETED",0)==10:break
                time.sleep(.05)
            if not saw_running:raise RuntimeError("batch completed before a running job could be interrupted")
            stop_owned(process);process=None;before=batch_state(url,organization,company,batch)[0]
            process=start_backend(environment,log);deadline=time.time()+90
            while time.time()<deadline:
                state=batch_state(url,organization,company,batch)
                if state[0].get("COMPLETED",0)==10:break
                time.sleep(.25)
            jobs,documents,ai,exports=batch_state(url,organization,company,batch)
            if jobs.get("COMPLETED",0)!=10 or sum(jobs.values())!=10:raise AssertionError(f"unexpected job states: {jobs}")
            if documents!=(10,10,10):raise AssertionError(f"document uniqueness failed: {documents}")
            if ai or exports:raise AssertionError(f"known deterministic batch unexpectedly used AI/exports: ai={ai}, exports={exports}")
            print(json.dumps({"status":"PASS","batch_id":batch,"interrupted_state":before,"final_jobs":jobs,"documents":documents[0],"ai_calls":ai,"exports":exports,"owned_process_only":True},sort_keys=True));return 0
        finally:
            if process:stop_owned(process)
            log.close()


if __name__=="__main__":raise SystemExit(main())
