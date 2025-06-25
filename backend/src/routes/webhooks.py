from fastapi import APIRouter, Request, HTTPException, Depends
from ..database.db import create_challenge_quota
from ..database.models import get_db
from svix.webhooks import Webhook
import os
import json

router = APIRouter()

@router.post("/clerk")
async def handle_user_created(request: Request, db=Depends(get_db)):
    webhook_secret = os.getenv("CLERK_WEBHOOK_SECRET")

    if not webhook_secret:
        raise HTTPException(status_code=500, detail="CLERK_WEBHOOK_SECRET not set")

    body = await request.body()
    payload = body.decode("utf-8")
    headers = dict(request.headers)

    try:
        wh = Webhook(webhook_secret)
        wh.verify(payload, headers)

        data = json.loads(payload)
        print("[WEBHOOK] Received event:", data.get("type"))

        if data.get("type") != "user.created":
            return {"status": "ignored"}

        user_data = data.get("data", {})
        user_id = user_data.get("id")
        print("[WEBHOOK] Creating quota for user:", user_id)

        create_challenge_quota(db, user_id)
        db.commit()  # <- KEY PART

        return {"status": "success"}
    except Exception as e:
        print("[WEBHOOK ERROR]", str(e))
        raise HTTPException(status_code=401, detail=str(e))
