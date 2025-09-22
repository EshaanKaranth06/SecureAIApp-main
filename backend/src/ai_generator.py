import os
import json
import re
import uuid
from typing import Dict, Any
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

HF_TOKEN = os.getenv("HF_API_KEY")

# Initialize HF Inference Client
client = InferenceClient(
    provider="hf-inference",
    api_key=HF_TOKEN,
)


def generate_challenge_with_ai(difficulty: str) -> Dict[str, Any]:
    system_prompt = """You are an expert coding challenge creator. 

Your task is to generate a coding question with multiple choice answers.
The question should be appropriate for the specified difficulty level.

For easy questions: Focus on basic syntax, simple operations, or common programming concepts.
For medium questions: Cover intermediate concepts like data structures, algorithms, or language features.
For hard questions: Include advanced topics, design patterns, optimization techniques, or complex algorithms.

Return the challenge in the following JSON structure:
{
    "title": "The question title",
    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
    "correct_answer_id": 0,
    "explanation": "Detailed explanation of why the correct answer is right"
}

 IMPORTANT: Output must be ONLY raw JSON. 
Do not include explanations, markdown, or extra text outside the JSON object.
"""

    rand_tag = str(uuid.uuid4())
    user_request = f"Generate a {difficulty} difficulty coding challenge. ID: {rand_tag}"

    try:
        # Call Hugging Face API
        response = client.chat.completions.create(
            model="HuggingFaceTB/SmolLM3-3B",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_request},
            ],
            temperature=0.7,
            max_tokens=800,
        )

        generated_text = response.choices[0].message["content"].strip()

        # --- DEBUG LOGGING ---
        print("---- RAW MODEL OUTPUT ----")
        print(generated_text)
        print("--------------------------")

        # Extract only the first JSON object using regex
        match = re.search(r'\{.*\}', generated_text, re.DOTALL)
        if not match:
            raise ValueError("No valid JSON found in model response")

        json_str = match.group(0)
        challenge_data = json.loads(json_str)

        # Validate required fields
        required_fields = ["title", "options", "correct_answer_id", "explanation"]
        for field in required_fields:
            if field not in challenge_data:
                raise ValueError(f"Missing required field: {field}")

        return challenge_data

    except Exception as e:
        print(f"[ERROR] {e}")
        return get_fallback_challenge()


def get_fallback_challenge() -> Dict[str, Any]:
    """Return a fallback challenge if the API fails"""
    print("[FALLBACK] Model failed — returning static challenge")
    return {
        "title": "Basic Python List Operation",
        "options": [
            "my_list.append(5)",
            "my_list.add(5)",
            "my_list.push(5)",
            "my_list.insert(5)",
        ],
        "correct_answer_id": 0,
        "explanation": "In Python, append() is the correct method to add an element to the end of a list."
    }
