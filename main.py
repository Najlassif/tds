import os
import sys
from io import StringIO
import traceback
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import types

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

class ErrorAnalysis(BaseModel):
    error_lines: List[int]

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
    Passes the failed code and crash information to Gemini AI via AI Pipe, 
    forcing it to respond only with structural line numbers.
    """
    # Hardcoded your token and set the target AI pipe endpoint URL
    client = genai.Client(
        api_key="eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjYzZjMwMDAyNTlAZHMuc3R1ZHkuaW1tLmFjLmluIiIsImloZCI6MTc1MTQ0NTk0NywiaXN6IjVraHR0cHM6Ly9haXBpcGUub3JnIiwidXNlckloIjoiYWlwaXBlXBlbWFwYSIsImV4cCI6MTc1MjA5NTM0N0030.x488EnS4i4ev3YBB8Q7uGum1MdAOi0OpwkHCEqfSAOs",
        http_options={"base_url": "https://aipipe.org"}
    )

    prompt = f"""
Analyze this Python code and its error traceback.
Identify the line number(s) where the error occurred.

CODE:
{code}

TRACEBACK:
{traceback_str}

Return the line number(s) where the error is located.
"""

    response = client.models.generate_content(
        model='gemini-2.0-flash-exp',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "error_lines": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.INTEGER)
                    )
                },
                required=["error_lines"]
            )
        )
    )

    result = ErrorAnalysis.model_validate_json(response.text)
    return result.error_lines

# ----------------------------------------------------
# 4. FASTAPI ENDPOINT ROUTE
# ----------------------------------------------------
@app.post("/code-interpreter/")
@app.post("/code-interpreter", response_model=CodeResponse)
async def interpret_code(request: CodeRequest):
    # Execute the incoming code string
    execution = execute_python_code(request.code)
    
    # If the execution went perfectly fine with no runtime flaws
    if execution["success"]:
        return CodeResponse(
            error=[], 
            result=execution["output"]
        )
    
    # If the program execution failed, use AI to pinpoint the broken line numbers
    error_lines = analyze_error_with_ai(request.code, execution["output"])
    
    return CodeResponse(
        error=error_lines, 
        result=execution["output"]
    )
