# src/database/db.py

from pymongo import MongoClient
from datetime import datetime, timedelta
from bson import ObjectId
from typing import Optional, List, Dict, Any, TYPE_CHECKING

# This is the key change to prevent circular imports at runtime.
# It allows type checkers (like in your IDE) to see the import,
# but Python doesn't execute it when running the app.
if TYPE_CHECKING:
    from .models import DatabaseManager

def get_challenge_quota(db_manager: "DatabaseManager", user_id: str) -> Optional[Dict[str, Any]]:
    """Get challenge quota for a user"""
    try:
        return db_manager.challenge_quotas.find_one({"user_id": user_id})
    except Exception as e:
        print(f"Error getting challenge quota: {e}")
        return None

def create_challenge_quota(db_manager: "DatabaseManager", user_id: str) -> Dict[str, Any]:
    """Create a new challenge quota for a user"""
    try:
        quota_doc = {
            "user_id": user_id,
            "quota_remaining": 50,  # Default quota
            "last_reset_date": datetime.now(),
            "created_at": datetime.now()
        }
        
        result = db_manager.challenge_quotas.insert_one(quota_doc)
        quota_doc["_id"] = result.inserted_id
        return quota_doc
    except Exception as e:
        print(f"Error creating challenge quota: {e}")
        raise

def reset_quota_if_needed(db_manager: "DatabaseManager", quota: Dict[str, Any]) -> Dict[str, Any]:
    """Reset quota if 24 hours have passed since last reset"""
    try:
        now = datetime.now()
        last_reset = quota.get("last_reset_date", now)
        
        if now - last_reset > timedelta(hours=24):
            updated_quota = db_manager.challenge_quotas.find_one_and_update(
                {"_id": quota["_id"]},
                {
                    "$set": {
                        "quota_remaining": 50,  # Reset to default
                        "last_reset_date": now
                    }
                },
                return_document=True  # Returns the updated document
            )
            return updated_quota if updated_quota else quota
        
        return quota
    except Exception as e:
        print(f"Error resetting quota: {e}")
        return quota

def create_challenge(
    db_manager: "DatabaseManager",
    difficulty: str,
    created_by: str,
    title: str,
    options: str,
    correct_answer_id: int,
    explanation: str
) -> Dict[str, Any]:
    """Create a new challenge"""
    try:
        challenge_doc = {
            "difficulty": difficulty,
            "created_by": created_by,
            "title": title,
            "options": options,
            "correct_answer_id": correct_answer_id,
            "explanation": explanation,
            "date_created": datetime.now()
        }
        
        result = db_manager.challenges.insert_one(challenge_doc)
        challenge_doc["_id"] = result.inserted_id
        return challenge_doc
    except Exception as e:
        print(f"Error creating challenge: {e}")
        raise

def get_user_challenges(db_manager: "DatabaseManager", user_id: str) -> List[Dict[str, Any]]:
    """Get all challenges created by a user"""
    try:
        return list(db_manager.challenges.find({"created_by": user_id}))
    except Exception as e:
        print(f"Error getting user challenges: {e}")
        return []

def update_challenge_quota(db_manager: "DatabaseManager", quota_id: ObjectId, decrement: int = 1) -> bool:
    """Update challenge quota by decrementing the remaining count"""
    try:
        result = db_manager.challenge_quotas.update_one(
            {"_id": quota_id},
            {"$inc": {"quota_remaining": -decrement}}
        )
        return result.modified_count > 0
    except Exception as e:
        print(f"Error updating challenge quota: {e}")
        return False