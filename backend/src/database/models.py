# database/models.py - Fixed MongoDB setup
from pymongo import MongoClient, ASCENDING
from datetime import datetime
import os
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List

load_dotenv()

# MongoDB connection
client = MongoClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017/"))

# Database name
DATABASE_NAME = os.getenv("DATABASE_NAME", "challenge_app")
db = client[DATABASE_NAME]

# Collections
challenges_collection = db.challenges
challenge_quotas_collection = db.challenge_quotas

class DatabaseManager:
    """MongoDB database manager with collection access"""
    
    def __init__(self):
        self.client = client
        self.db = db
        self.challenges = challenges_collection
        self.challenge_quotas = challenge_quotas_collection
        self._create_indexes()
    
    def _create_indexes(self):
        """Create necessary indexes for performance"""
        try:
            # Index for challenge_quotas
            self.challenge_quotas.create_index([("user_id", ASCENDING)], unique=True)
            
            # Indexes for challenges
            self.challenges.create_index([("created_by", ASCENDING)])
            self.challenges.create_index([("difficulty", ASCENDING)])
            self.challenges.create_index([("date_created", ASCENDING)])
            
            print("MongoDB indexes created successfully")
        except Exception as e:
            print(f"Index creation warning: {e}")

# Global database manager instance
db_manager = DatabaseManager()

def get_db() -> DatabaseManager:
    """
    Database dependency for FastAPI
    Returns the DatabaseManager instance directly (not a context manager)
    """
    return db_manager

# Alternative dependency if you need connection management
def get_db_with_connection():
    """Alternative dependency with explicit connection management"""
    try:
        # Test connection
        db_manager.client.admin.command('ping')
        yield db_manager
    except Exception as e:
        print(f"Database connection error: {e}")
        raise
    finally:
        # MongoDB connections are pooled, no explicit closing needed for individual requests
        pass


# database/db.py - Fixed database operations
from pymongo import MongoClient
from datetime import datetime, timedelta
from bson import ObjectId
from typing import Optional, List, Dict, Any
from .models import DatabaseManager

def get_challenge_quota(db_manager: DatabaseManager, user_id: str) -> Optional[Dict[str, Any]]:
    """Get challenge quota for a user"""
    try:
        return db_manager.challenge_quotas.find_one({"user_id": user_id})
    except Exception as e:
        print(f"Error getting challenge quota: {e}")
        return None

def create_challenge_quota(db_manager: DatabaseManager, user_id: str) -> Dict[str, Any]:
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

def reset_quota_if_needed(db_manager: DatabaseManager, quota: Dict[str, Any]) -> Dict[str, Any]:
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
    db_manager: DatabaseManager,
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
            "date_created": datetime.now()  # Changed from created_at to match your original field name
        }
        
        result = db_manager.challenges.insert_one(challenge_doc)
        challenge_doc["_id"] = result.inserted_id
        return challenge_doc
    except Exception as e:
        print(f"Error creating challenge: {e}")
        raise

def get_user_challenges(db_manager: DatabaseManager, user_id: str) -> List[Dict[str, Any]]:
    """Get all challenges created by a user"""
    try:
        return list(db_manager.challenges.find({"created_by": user_id}))
    except Exception as e:
        print(f"Error getting user challenges: {e}")
        return []

def update_challenge_quota(db_manager: DatabaseManager, quota_id: ObjectId, decrement: int = 1) -> bool:
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


# Fixed FastAPI routes
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

# Updated imports
from ..ai_generator import generate_challenge_with_ai
from ..database.db import (
    get_challenge_quota,
    create_challenge,
    create_challenge_quota,
    reset_quota_if_needed,
    get_user_challenges,
    update_challenge_quota
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
    
    doc_copy = doc.copy()
    
    # Convert ObjectId to string
    if "_id" in doc_copy:
        doc_copy["id"] = str(doc_copy["_id"])
        del doc_copy["_id"]
    
    # Convert datetime objects to ISO format strings
    for key, value in doc_copy.items():
        if isinstance(value, datetime):
            doc_copy[key] = value.isoformat()
        elif isinstance(value, ObjectId):
            doc_copy[key] = str(value)
    
    return doc_copy

@router.post("/generate-challenge")
async def generate_challenge(
    request: ChallengeRequest, 
    request_obj: Request, 
    db: DatabaseManager = Depends(get_db)
):
    try:
        user_details = authenticate_and_get_user_details(request_obj)
        user_id = user_details.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")

        print(f"Processing challenge request for user: {user_id}")

        # Get or create quota
        quota = get_challenge_quota(db, user_id)
        if not quota:
            print(f"Creating new quota for user: {user_id}")
            quota = create_challenge_quota(db, user_id)

        # Reset quota if needed
        quota = reset_quota_if_needed(db, quota)

        # Check quota
        if quota.get("quota_remaining", 0) <= 0:
            raise HTTPException(status_code=429, detail="Quota exhausted")

        print(f"Generating AI challenge with difficulty: {request.difficulty}")
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
        update_success = update_challenge_quota(db, quota["_id"], 1)
        if not update_success:
            print("Warning: Failed to update quota")

        # Serialize response
        response_challenge = serialize_mongo_doc(new_challenge)
        
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
        print(f"Error in generate_challenge: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/quota")
async def get_quota(
    request: Request, 
    db: DatabaseManager = Depends(get_db)
):
    try:
        user_details = authenticate_and_get_user_details(request)
        user_id = user_details.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")

        print(f"Getting quota for user: {user_id}")

        # Get or create quota
        quota = get_challenge_quota(db, user_id)
        if not quota:
            print(f"Creating new quota for user: {user_id}")
            quota = create_challenge_quota(db, user_id)

        # Reset quota if needed
        quota = reset_quota_if_needed(db, quota)
        
        # Serialize quota for JSON response
        serialized_quota = serialize_mongo_doc(quota)
        
        return {
            "user_id": serialized_quota.get("user_id"),
            "quota_remaining": serialized_quota.get("quota_remaining", 0),
            "last_reset_date": serialized_quota.get("last_reset_date")
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_quota: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/my-history")
async def my_history(
    request: Request, 
    db: DatabaseManager = Depends(get_db)
):
    try:
        user_details = authenticate_and_get_user_details(request)
        user_id = user_details.get("user_id")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")

        print(f"Getting history for user: {user_id}")

        # Get user challenges
        challenges = get_user_challenges(db, user_id)
        
        # Serialize challenges for JSON response
        serialized_challenges = []
        for challenge in challenges:
            serialized_challenge = serialize_mongo_doc(challenge)
            
            # Parse options if it's a JSON string
            if "options" in serialized_challenge and isinstance(serialized_challenge["options"], str):
                try:
                    serialized_challenge["options"] = json.loads(serialized_challenge["options"])
                except json.JSONDecodeError:
                    pass  # Keep as string if not valid JSON
            
            serialized_challenges.append(serialized_challenge)
        
        return {"challenges": serialized_challenges}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in my_history: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))