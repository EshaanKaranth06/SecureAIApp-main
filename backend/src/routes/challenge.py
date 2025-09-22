from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

from ..ai_generator import generate_challenge_with_ai
from ..database.db import (
    get_challenge_quota,
    create_challenge,
    create_challenge_quota,
    reset_quota_if_needed,
    get_user_challenges
)
from ..utils import authenticate_and_get_user_details
from ..database.models import get_db, DatabaseManager
import json
from datetime import datetime
from bson import ObjectId

router = APIRouter()

class ChallengeRequest(BaseModel):
    difficulty: str
    
    class Config:
        json_schema_extra = {"example": {"difficulty": "easy"}}

def serialize_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MongoDB document to JSON serializable format"""
    if doc is None:
        return None
    
    # Convert ObjectId to string
    if "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    
    # Convert datetime objects to ISO format strings
    for key, value in doc.items():
        if isinstance(value, datetime):
            doc[key] = value.isoformat()
        elif isinstance(value, ObjectId):
            doc[key] = str(value)
    
    return doc

def serialize_mongo_docs(docs: list) -> list:
    """Convert list of MongoDB documents to JSON serializable format"""
    return [serialize_mongo_doc(doc.copy()) for doc in docs if doc is not None]

@router.post("/generate-challenge")
async def generate_challenge(
    request: ChallengeRequest, 
    request_obj: Request, 
    db: DatabaseManager = Depends(get_db)
):
    try:
        user_details = authenticate_and_get_user_details(request_obj)
        user_id = user_details.get("user_id")

        # Get or create quota
        quota = get_challenge_quota(db, user_id)
        if not quota:
            quota = create_challenge_quota(db, user_id)

        # Reset quota if needed
        quota = reset_quota_if_needed(db, quota)

        # Check quota
        if quota.get("quota_remaining", 0) <= 0:
            raise HTTPException(status_code=429, detail="Quota exhausted")

        # Generate challenge with AI
        challenge_data = generate_challenge_with_ai(request.difficulty)

        # Create challenge document
        new_challenge = create_challenge(
            db_manager=db,
            difficulty=request.difficulty,
            created_by=user_id,
            title=challenge_data["title"],
            options=json.dumps(challenge_data["options"]),
            correct_answer_id=challenge_data["correct_answer_id"],
            explanation=challenge_data["explanation"]
        )

        # Update quota (decrement by 1)
        db.challenge_quotas.update_one(
            {"_id": quota["_id"]},
            {"$inc": {"quota_remaining": -1}}
        )

        # Serialize response
        response_challenge = serialize_mongo_doc(new_challenge.copy())
        
        return {
            "id": response_challenge["id"],
            "difficulty": request.difficulty,
            "title": response_challenge["title"],
            "options": json.loads(response_challenge["options"]),
            "correct_answer_id": response_challenge["correct_answer_id"],
            "explanation": response_challenge["explanation"],
            "timestamp": response_challenge.get("date_created", datetime.now().isoformat())
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/my-history")
async def my_history(
    request: Request, 
    db: DatabaseManager = Depends(get_db)
):
    try:
        user_details = authenticate_and_get_user_details(request)
        user_id = user_details.get("user_id")

        # Get user challenges
        challenges = get_user_challenges(db, user_id)
        
        # Serialize challenges for JSON response
        serialized_challenges = []
        for challenge in challenges:
            challenge_copy = challenge.copy()
            serialized_challenge = serialize_mongo_doc(challenge_copy)
            
            # Parse options if it's a JSON string
            if "options" in serialized_challenge and isinstance(serialized_challenge["options"], str):
                try:
                    serialized_challenge["options"] = json.loads(serialized_challenge["options"])
                except json.JSONDecodeError:
                    pass  # Keep as string if not valid JSON
            
            serialized_challenges.append(serialized_challenge)
        
        return {"challenges": serialized_challenges}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/quota")
async def get_quota(
    request: Request, 
    db: DatabaseManager = Depends(get_db)
):
    try:
        user_details = authenticate_and_get_user_details(request)
        user_id = user_details.get("user_id")

        # Get or create quota
        quota = get_challenge_quota(db, user_id)
        if not quota:
            quota = create_challenge_quota(db, user_id)

        # Reset quota if needed
        quota = reset_quota_if_needed(db, quota)
        
        # Serialize quota for JSON response
        serialized_quota = serialize_mongo_doc(quota.copy())
        
        return {
            "id": serialized_quota.get("id"),
            "user_id": serialized_quota.get("user_id"),
            "quota_remaining": serialized_quota.get("quota_remaining", 0),
            "last_reset_date": serialized_quota.get("last_reset_date")
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Additional utility endpoints for MongoDB

@router.get("/quota/reset")
async def force_reset_quota(
    request: Request, 
    db: DatabaseManager = Depends(get_db)
):
    """Force reset quota (useful for testing or admin purposes)"""
    try:
        user_details = authenticate_and_get_user_details(request)
        user_id = user_details.get("user_id")

        # Update quota directly
        result = db.challenge_quotas.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "quota_remaining": 50,  # Reset to default
                    "last_reset_date": datetime.now()
                }
            },
            upsert=True
        )
        
        if result.modified_count > 0 or result.upserted_id:
            return {"message": "Quota reset successfully", "quota_remaining": 50}
        else:
            raise HTTPException(status_code=404, detail="User quota not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/challenges/count")
async def get_challenge_count(
    request: Request, 
    db: DatabaseManager = Depends(get_db)
):
    """Get total number of challenges created by user"""
    try:
        user_details = authenticate_and_get_user_details(request)
        user_id = user_details.get("user_id")

        # Count challenges
        count = db.challenges.count_documents({"created_by": user_id})
        
        return {"total_challenges": count}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/challenges/{challenge_id}")
async def delete_challenge(
    challenge_id: str,
    request: Request, 
    db: DatabaseManager = Depends(get_db)
):
    """Delete a specific challenge (only by the creator)"""
    try:
        user_details = authenticate_and_get_user_details(request)
        user_id = user_details.get("user_id")

        # Validate ObjectId format
        try:
            obj_id = ObjectId(challenge_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid challenge ID format")

        # Delete challenge (only if created by current user)
        result = db.challenges.delete_one({
            "_id": obj_id,
            "created_by": user_id
        })

        if result.deleted_count > 0:
            return {"message": "Challenge deleted successfully"}
        else:
            raise HTTPException(
                status_code=404, 
                detail="Challenge not found or you don't have permission to delete it"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))