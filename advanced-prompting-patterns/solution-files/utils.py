import json
from pydantic import ValidationError

def extract_json(text: str):
    """Extract the first JSON object from a string."""
    text = text.strip()

    # Remove markdown code fences if present
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text.split("\n", 1)[1] if "\n" in text else text

    # Find the first opening brace and parse from there
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", text, 0)

    return json.loads(text[start:])

def validate_json_output(response_text, model_class):
    """
    Parse JSON from LLM response and validate against Pydantic model.
    Returns (success, result_or_errors)
    """
    try:
        data = extract_json(response_text)
        validated = model_class(**data)
        return True, validated

    except json.JSONDecodeError as e:
        return False, f"JSON parsing error: {e}"

    except ValidationError as e:
        return False, f"Validation errors: {e.errors()}"