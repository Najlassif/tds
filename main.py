import os
import sys
from io import StringIO
import traceback
from typing import List
import json
import requests

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ----------------------------------------------------
# 1. INITIALIZE & CORS SETUP
# ----------------------------------------------------
app = FastAPI()

# Enable CORS so the testing autograder can securely access your app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------
# 2. DATA CONTAINERS / SCHEMAS
# ----------------------------------------------------
class CodeRequest(BaseModel):
    code: str

class CodeResponse(BaseModel):
    error: List[int]
    result: str

# ----------------------------------------------------
# 3. HELPER LOGIC FUNCTIONS
# ----------------------------------------------------
def execute_python_code(code: str) -> dict:
    """
    Execute Python code locally and capture either the text output 
    or the exact crash information (traceback).
    """
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        exec(code)
        output = sys.stdout.getvalue()
        return {"success": True, "output": output}

    except Exception as e:
        output = traceback.format_exc()
        return {"success": False, "output": output}

    finally:
        sys.stdout = old_stdout

def analyze_error_with_ai(code: str, traceback_str: str) -> List[int]:
    """
    Passes the failed code and crash information to the LLM via AI Pipe.
    Uses robust prompt parsing to guarantee line extraction.
    """
    token = "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjYzZjMwMDAyNTlAZHMuc3R1ZHkuaW1tLmFjLmluIiIsImloZCI6MTc1MTQ0NTk0NywiaXN6IjVraHR0cHM6Ly9haXBpcGUub3JnIiwidXNlckloIjoiYWlwaXBlXBlbWFwYSIsImV4cCI6MTc1MjA5NTM0N0030.x488EnS4i4ev3YBB8Q7uGum1MdAOi0OpwkHCEqfSAOs"
    
    # Using the standard AI Pipe endpoint mapping
    url = "https://aipipe.org"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    prompt = f"""
Analyze this Python code and its error traceback.
Identify the exact line number(s) where the error occurred.

CODE:
{code}

TRACEBACK:
{traceback_str}

Return the line number(s) where the error is located. You MUST respond with a valid JSON object matching this schema exactly:
{{
    "error_lines": [3]
}}
Do not write any markdown code blocks or explanations outside the JSON object.
"""

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response_json = response.json()
        
        ai_content = response_json["choices"][0]["message"]["content"]
        
        # Strip code block wrappers if the AI accidentally added them
        ai_content = ai_content.replace("```json", "").replace("```", "").strip()
        
        data = json.loads(ai_content)
        lines = data.get("error_lines", [])
        
        # Safety fallback parsing if the list returned strings instead of ints
        return [int(x) for x in lines if str(x).isdigit()]
    except Exception as e:
        print("AI Processing Exception Error:", str(e))
        
        # Fallback Parser: Try to extract line number directly from raw traceback string 
        # if the AI call fails or gives a parsing anomaly.
        try:
            for line in traceback_str.split('\n'):
                if 'File "<string>", line' in line:
                    parts = line.split(',')
                    for p in parts:
                        if 'line' in p:
                            num = ''.join(c for c in p if c.isdigit())
                            if num:
                                return [int(num)]
        except:
            pass
        return []

# ----------------------------------------------------
# 4. FASTAPI ENDPOINT ROUTES
# ----------------------------------------------------
@app.post("/code-interpreter/")
@app.post("/code-interpreter", response_model=CodeResponse)
async def interpret_code(request: CodeRequest):
    execution = execute_python_code(request.code)
    
    if execution["success"]:
        return CodeResponse(
            error=[], 
            result=execution["output"]
        )
    
    error_lines = analyze_error_with_ai(request.code, execution["output"])
    
    return CodeResponse(
        error=error_lines, 
        result=execution["output"]
    )
