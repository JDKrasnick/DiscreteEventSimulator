from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.policy_registry import registry

router = APIRouter()


@router.get("/policies")
def list_policies():
    return registry.list_grouped()


@router.post("/policies/upload", status_code=201)
async def upload_policy(file: UploadFile = File(...)):
    try:
        content = await file.read()
        policies = registry.upload(file.filename or "policy.py", content)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "uploaded": [
            {
                "id": policy.id,
                "name": policy.name,
                "kind": policy.kind,
                "source_file": policy.source_file,
                "description": policy.description,
            }
            for policy in policies
        ]
    }
