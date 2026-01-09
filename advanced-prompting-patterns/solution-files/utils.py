import json
from pydantic import ValidationError

def validate_json_output(response_text, model_class):
    """
    Parse JSON from LLM response and validate against Pydantic model.
    Returns (success, result_or_errors)
    """
    try:
        # Extract JSON (handles markdown code blocks if present)
        json_text = response_text.strip()
        if json_text.startswith("```json"):
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif json_text.startswith("```"):
            json_text = json_text.split("```")[1].split("```")[0].strip()

        # Parse and validate
        data = json.loads(json_text)
        validated = model_class(**data)
        return True, validated

    except json.JSONDecodeError as e:
        return False, f"JSON parsing error: {str(e)}"

    except ValidationError as e:
        return False, f"Validation errors: {e.errors()}"