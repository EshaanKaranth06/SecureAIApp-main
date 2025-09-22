from fastapi import APIRouter, Request, HTTPException, Depends
from ..database.db import create_challenge_quota
from ..database.models import get_db, DatabaseManager
from svix.webhooks import Webhook
import os
import json

router = APIRouter()

@router.post("/clerk")
async def handle_user_created(request: Request, db: DatabaseManager = Depends(get_db)):
    webhook_secret = os.getenv("CLERK_WEBHOOK_SECRET")
    
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="CLERK_WEBHOOK_SECRET not set")
    
    body = await request.body()
    payload = body.decode("utf-8")
    headers = dict(request.headers)
    
    try:
        # Verify webhook signature
        wh = Webhook(webhook_secret)
        wh.verify(payload, headers)
        
        # Parse webhook data
        data = json.loads(payload)
        event_type = data.get("type")
        print(f"[WEBHOOK] Received event: {event_type}")
        
        # Handle different event types
        if event_type == "user.created":
            return await handle_user_created_event(data, db)
        elif event_type == "user.deleted":
            return await handle_user_deleted_event(data, db)
        elif event_type == "user.updated":
            return await handle_user_updated_event(data, db)
        else:
            print(f"[WEBHOOK] Ignoring event type: {event_type}")
            return {"status": "ignored", "event_type": event_type}
    
    except Exception as e:
        print(f"[WEBHOOK ERROR] {str(e)}")
        raise HTTPException(status_code=401, detail=str(e))

async def handle_user_created_event(data: dict, db: DatabaseManager) -> dict:
    """Handle user.created event from Clerk"""
    try:
        user_data = data.get("data", {})
        user_id = user_data.get("id")
        
        if not user_id:
            print("[WEBHOOK ERROR] No user ID found in webhook data")
            raise HTTPException(status_code=400, detail="No user ID found in webhook data")
        
        print(f"[WEBHOOK] Creating quota for user: {user_id}")
        
        # Check if quota already exists (prevent duplicates)
        existing_quota = db.challenge_quotas.find_one({"user_id": user_id})
        if existing_quota:
            print(f"[WEBHOOK] Quota already exists for user: {user_id}")
            return {
                "status": "success", 
                "message": "User quota already exists",
                "user_id": user_id
            }
        
        # Create challenge quota for new user
        quota = create_challenge_quota(db, user_id)
        
        # Log additional user info for debugging
        email = user_data.get("email_addresses", [{}])[0].get("email_address")
        username = user_data.get("username")
        print(f"[WEBHOOK] Created quota for user: {user_id}, email: {email}, username: {username}")
        
        return {
            "status": "success", 
            "message": "User quota created successfully",
            "user_id": user_id,
            "quota_id": str(quota["_id"]) if "_id" in quota else None
        }
        
    except Exception as e:
        print(f"[WEBHOOK ERROR] Failed to create user quota: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create user quota: {str(e)}")

async def handle_user_deleted_event(data: dict, db: DatabaseManager) -> dict:
    """Handle user.deleted event from Clerk"""
    try:
        user_data = data.get("data", {})
        user_id = user_data.get("id")
        
        if not user_id:
            print("[WEBHOOK ERROR] No user ID found in webhook data")
            return {"status": "error", "message": "No user ID found"}
        
        print(f"[WEBHOOK] Deleting data for user: {user_id}")
        
        # Delete user's challenge quota
        quota_result = db.challenge_quotas.delete_one({"user_id": user_id})
        
        # Delete user's challenges (optional - you might want to keep them for analytics)
        challenges_result = db.challenges.delete_many({"created_by": user_id})
        
        print(f"[WEBHOOK] Deleted {quota_result.deleted_count} quota(s) and {challenges_result.deleted_count} challenge(s) for user: {user_id}")
        
        return {
            "status": "success",
            "message": "User data deleted successfully",
            "user_id": user_id,
            "deleted_quotas": quota_result.deleted_count,
            "deleted_challenges": challenges_result.deleted_count
        }
        
    except Exception as e:
        print(f"[WEBHOOK ERROR] Failed to delete user data: {str(e)}")
        # Don't raise exception here - user deletion should still succeed even if cleanup fails
        return {
            "status": "partial_success",
            "message": f"User deleted but cleanup failed: {str(e)}",
            "user_id": user_id
        }

async def handle_user_updated_event(data: dict, db: DatabaseManager) -> dict:
    """Handle user.updated event from Clerk (optional)"""
    try:
        user_data = data.get("data", {})
        user_id = user_data.get("id")
        
        print(f"[WEBHOOK] User updated: {user_id}")
        
        # You might want to update user-related data here
        # For now, just log the event
        
        return {
            "status": "success",
            "message": "User update processed",
            "user_id": user_id
        }
        
    except Exception as e:
        print(f"[WEBHOOK ERROR] Failed to handle user update: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to handle user update: {str(e)}"
        }

# Additional webhook endpoints for other Clerk events (optional)
@router.post("/clerk/session")
async def handle_session_events(request: Request, db: DatabaseManager = Depends(get_db)):
    """Handle session-related events from Clerk"""
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
        event_type = data.get("type")
        
        print(f"[SESSION WEBHOOK] Received event: {event_type}")
        
        # Handle session events (session.created, session.ended, etc.)
        if event_type in ["session.created", "session.ended", "session.removed"]:
            # Log session activity or update user activity tracking
            user_id = data.get("data", {}).get("user_id")
            if user_id:
                print(f"[SESSION WEBHOOK] {event_type} for user: {user_id}")
                # You could track user activity, last login, etc. here
        
        return {"status": "success", "event_type": event_type}
        
    except Exception as e:
        print(f"[SESSION WEBHOOK ERROR] {str(e)}")
        raise HTTPException(status_code=401, detail=str(e))

# Health check endpoint for webhook testing
@router.get("/clerk/health")
async def webhook_health_check():
    """Health check endpoint for Clerk webhooks"""
    return {
        "status": "healthy",
        "service": "clerk_webhooks",
        "webhook_secret_configured": bool(os.getenv("CLERK_WEBHOOK_SECRET"))
    }