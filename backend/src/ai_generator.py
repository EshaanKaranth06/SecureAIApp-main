import os
import json
import requests
from typing import Dict, Any
from dotenv import load_dotenv
import uuid
load_dotenv()

HF_API_URL = "https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1"
HF_TOKEN = os.getenv("HF_API_KEY")

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

Make sure the options are plausible but with only one clearly correct answer.
Only return valid JSON, no additional text or formatting.
"""

      
    rand_tag = str(uuid.uuid4())
    prompt = f"<s>[INST] <<SYS>>\n{system_prompt}\n<</SYS>>\n\nGenerate a {difficulty} difficulty coding challenge. ID: {rand_tag} [/INST]"


    
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 800,
            "temperature": 0.7,
            "do_sample": True,
            "top_p": 0.95,
            "repetition_penalty": 1.1,
            "return_full_text": False,
            "stop": ["</s>", "[INST]"]
        }
    }
    
    try:
        response = requests.post(HF_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        # Extract the generated text from Mixtral response
        if isinstance(result, list) and len(result) > 0:
            generated_text = result[0].get("generated_text", "")
        elif isinstance(result, dict):
            generated_text = result.get("generated_text", "")
        else:
            raise ValueError("Unexpected response format")
        
        # Clean up the response - remove any chat formatting artifacts
        generated_text = generated_text.strip()
        if generated_text.startswith("[/INST]"):
            generated_text = generated_text[7:].strip()
        
        # Try to extract JSON from the response
        # Look for JSON content between curly braces
        start_idx = generated_text.find('{')
        end_idx = generated_text.rfind('}') + 1
        
        if start_idx != -1 and end_idx > start_idx:
            json_str = generated_text[start_idx:end_idx]
            try:
                challenge_data = json.loads(json_str)
            except json.JSONDecodeError:
                # Try to clean up common JSON issues
                json_str = json_str.replace('\n', ' ').replace('\r', '')
                # Fix trailing commas
                json_str = json_str.replace(',}', '}').replace(',]', ']')
                challenge_data = json.loads(json_str)
        else:
            # If no JSON found, try parsing the entire response
            challenge_data = json.loads(generated_text)
        
        # Validate required fields
        required_fields = ["title", "options", "correct_answer_id", "explanation"]
        for field in required_fields:
            if field not in challenge_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Ensure options is a list with 4 items
        if not isinstance(challenge_data["options"], list) or len(challenge_data["options"]) != 4:
            raise ValueError("Options must be a list with exactly 4 items")
        
        # Ensure correct_answer_id is valid
        if not isinstance(challenge_data["correct_answer_id"], int) or not (0 <= challenge_data["correct_answer_id"] <= 3):
            raise ValueError("correct_answer_id must be an integer between 0 and 3")
        
        return challenge_data
    
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return get_fallback_challenge()
    except json.JSONDecodeError as e:
        print(f"JSON parsing failed: {e}")
        print(f"Raw response: {generated_text if 'generated_text' in locals() else 'No response'}")
        return get_fallback_challenge()
    except Exception as e:
        print(f"Unexpected error: {e}")
        return get_fallback_challenge()

def get_fallback_challenge() -> Dict[str, Any]:
    """Return a fallback challenge if the API fails"""
    print("[FALLBACK] Mixtral failed — returning static challenge")
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

# Example usage
if __name__ == "__main__":
    # Test the function with different difficulties
    for difficulty in ["easy", "medium", "hard"]:
        print(f"\n=== {difficulty.upper()} CHALLENGE ===")
        challenge = generate_challenge_with_ai(difficulty)
        print(json.dumps(challenge, indent=2))