"""One synthetic end-to-end local-model -> draft action -> preview check."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import psycopg

from v2.backend.app.hybrid_ai.proposal import LOCAL_PROPOSAL_JSON_SCHEMA, validate_proposal
from v2.backend.app.hybrid_ai.providers import LocalAiService
from v2.backend.app.hybrid_ai.template_actions import TemplateActionAdapter
from v2.backend.app.infrastructure.postgres_migrations import apply_migrations
from v2.backend.app.template_studio.models import StudioContext
from v2.backend.app.template_studio.repository import TemplateRepository
from v2.backend.app.template_studio.service import TemplateStudioService


ROOT=Path(__file__).resolve().parents[2]


def env_value(name: str) -> str:
    for line in (ROOT/".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name+"="): return line.split("=",1)[1].strip().strip('"')
    raise RuntimeError(f"{name} is not configured")


def main() -> None:
    url=env_value("POSTGRES_TEST_DATABASE_URL");key=(ROOT/"local_tools/llama.cpp/api-keys.txt").read_text().strip()
    provider=LocalAiService(model=str(ROOT/"local_models/Qwen3-1.7B-Q4_K_M.gguf"),timeout_seconds=120,api_key=key)
    result=provider.complete([
        {"role":"system","content":"Return one allowlisted Template Action JSON proposal only. Never approve, post, use SQL, shell, or files."},
        {"role":"user","content":"Bank columns Date, Narration, Debit, Credit, Balance. Propose exactly one create_table action for a DRAFT mapping."},
    ],LOCAL_PROPOSAL_JSON_SCHEMA)
    proposal=validate_proposal(result.payload,provider=result.provider,model=result.model,prompt_version="phase5b-runtime")
    if len(proposal.actions)!=1 or proposal.actions[0].action!="create_table":
        raise RuntimeError("local model did not produce the required safe table action")

    connection=psycopg.connect(url);apply_migrations(connection)
    org,company,user=uuid4(),uuid4(),uuid4()
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO organizations(id,name) VALUES(%s,%s)",(org,f"Phase5B synthetic {org}"))
        cursor.execute("INSERT INTO companies(id,organization_id,name,tally_company_name) VALUES(%s,%s,'Phase5B synthetic','Phase5B synthetic')",(company,org))
        cursor.execute("INSERT INTO users(id,organization_id,email,display_name,status) VALUES(%s,%s,%s,'Phase5B synthetic','ACTIVE')",(user,org,f"{user}@example.invalid"))
    connection.commit();connection.close()
    studio=TemplateStudioService(TemplateRepository(lambda:psycopg.connect(url)))
    context=StudioContext(org,company,user,frozenset({"ADMIN"}))
    created=studio.create_family(context,"Phase5B synthetic bank","BANK",mode="GENERIC")
    version=created["version"]
    selection={"box":{"x0":.05,"y0":.2,"x1":.95,"y1":.8},"columns":[
        {"boundary":.18,"field":"date"},{"boundary":.48,"field":"narration"},
        {"boundary":.65,"field":"debit"},{"boundary":.82,"field":"credit"},{"boundary":.98,"field":"balance"}]}
    evidence={"pages":[{"page_number":1,"tables":[{"bounding_box":{"x0":5,"y0":20,"x1":95,"y1":80,"page_width":100,"page_height":100},
        "rows":[{"cells":[{"text":"2026-08-09"},{"text":"Synthetic"},{"text":"100"},{"text":"0"},{"text":"900"}]}]}]}]}
    applied=TemplateActionAdapter(studio).apply(context,version["id"],version["revision"],proposal.actions[0],selection,evidence)
    print(json.dumps({"synthetic_only":True,"model_action":proposal.actions[0].action,
        "draft_status":applied.saved["status"],"new_revision":applied.saved["revision"],
        "deterministic_preview_ran":True,"preview_validation":applied.preview["validation"],
        "human_approval_required":applied.human_approval_required},default=str,indent=2))


if __name__=="__main__":main()
