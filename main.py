import os
import sys
from io import StringIO
import traceback
from typing import List
import json
import re
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
    Passes the failed code and crash information to Gemini AI via AI Pipe.
    Parses out integers directly to eliminate structural JSON matching failures.
    """
    token = "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjYzZjMwMDAyNTlAZHMuc3R1ZHkuaW1tLmFjLmluIiIsImloZCI6MTc1MTQ0NTk0NywiaXN6IjVraHR0cHM6Ly9haXBpcGUub3JnIiwidXNlckloIjoiYWlwaXBlXBlbWFwYSIsImV4cCI6MTc1MjA5NTM0N0030.x488EnS4i4ev3YBB8Q7uGum1MdAOi0OpwkHCEqfSAOs"
    url = "https://aipipe.org"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # Number the rows visually so the LLM doesn't guess or offset the indexes
    numbered_lines = []
    for idx, line in enumerate(code.splitlines(), start=1):
        numbered_lines.append(f"Line {idx}: {line}")
    code_with_numbers = "\n".join(numbered_lines)

    prompt = f"""
Identify the EXACT line number(s) in the python script where the execution failure/crash originates.
Look closely at the traceback file log to match the line index accurately.

CODE WITH LINE NUMBERS:
{code_with_numbers}

TRACEBACK LOG:
{traceback_str}

Respond ONLY with the raw integers inside a comma-separated list bracket (e.g., [2] or [3, 4]). Do not add extra text explanation.
"""

    payload = {
        "model": "google/gemini-2.0-flash-lite-001",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0  # Keep choices strict and predictable
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response_json = response.json()
        ai_content = response_json["choices"][0]["message"]["content"]
        
        # Pull all integers out from the AI's textual answer using regular expressions
        numbers = [int(num) for num in re.findall(r'\d+', ai_content)]
        
        # Cross-validate to prevent the AI from returning line numbers larger than the code block length
        total_lines = len(code.splitlines())
        valid_numbers = [n for n in numbers if 1 <= n <= total_lines]
        
        return list(set(valid_numbers))
    except Exception as e:
        print("AI Extraction Fallback:", str(e))
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
