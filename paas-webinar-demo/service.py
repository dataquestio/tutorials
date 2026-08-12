from openai import OpenAI
from dotenv import load_dotenv
import json
import os

load_dotenv()

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url="https://api.openai.com/v1"
)

def optimize_prompt(prompt: str, goal: str) -> dict:
    """Send a prompt to the LLM for optimization and return structured results."""

    system_message = """You are a prompt engineering expert. Your job is to improve
prompts so they produce better results from language models.

You will receive an original prompt and a goal describing what the prompt should accomplish.
Return your response as a JSON object with exactly these fields:
- "optimized_prompt": the improved version of the prompt
- "changes": a brief explanation of what you improved and why

Return ONLY the JSON object. No markdown formatting, no extra text."""

    user_message = f"""Original prompt: {prompt}

Goal: {goal}

Optimize this prompt to better achieve the stated goal."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        response_format={"type": "json_object"},
        temperature=0.7
    )

    result_text = response.choices[0].message.content

    try:
        result = json.loads(result_text)
    except json.JSONDecodeError:
        raise ValueError(
            f"LLM returned invalid JSON: {result_text[:200]}"
        )

    if "optimized_prompt" not in result or "changes" not in result:
        raise ValueError(
            f"LLM response missing required fields. Got: {list(result.keys())}"
        )

    return {
        "original_prompt": prompt,
        "optimized_prompt": result["optimized_prompt"],
        "changes": result["changes"]
    }