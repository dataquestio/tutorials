from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from service import optimize_prompt
import logging

logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}

class PromptRequest(BaseModel):
    prompt: str = Field(
        description="The original prompt to optimize"
    )
    goal: str = Field(
        description="What the prompt should accomplish"
    )
    model_config = {"extra": "forbid"}

class PromptResponse(BaseModel):
    original_prompt: str = Field(
        description="The original prompt that was submitted"
    )
    optimized_prompt: str = Field(
        description="The improved version of the prompt"
    )
    changes: str = Field(
        description="Explanation of what was improved and why"
    )

@app.post("/optimize", response_model=PromptResponse)
def optimize_prompt_endpoint(request: PromptRequest):
    try:
        result = optimize_prompt(request.prompt, request.goal)
    except ValueError as e:
        logger.error(f"Optimization failed: {e}")
        raise HTTPException(status_code=502, detail="Invalid upstream LLM response. Please retry.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please try again."
        )

    return PromptResponse(**result)