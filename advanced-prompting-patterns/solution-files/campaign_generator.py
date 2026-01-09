from conversation_manager import ConversationManager
from prompt_templates import build_campaign_prompt, build_extract_prompt, build_draft_prompt
from models import CampaignBrief, ExtractedProductInfo
from utils import validate_json_output

TEMPERATURE = 0.2

def generate_campaign_brief(factsheet, max_retries=3):
    """Generate a validated campaign brief with automatic repair."""
    conversation = ConversationManager()

    initial_prompt = build_campaign_prompt(factsheet)
    response = conversation.chat_completion(initial_prompt, temperature=TEMPERATURE)

    print("Initial response:")
    print(response)
    print()

    success, result = validate_json_output(response, CampaignBrief)

    if success:
        print("✓ Valid on first attempt!")
        return result

    print(f"✗ Validation failed: {result}")
    print()

    retries = 0
    last_error = result

    while retries < max_retries:
        print(f"Attempting repair {retries + 1}/{max_retries}...")

        repair_prompt = f"""
The JSON you provided had validation errors:

{last_error}

Please provide corrected JSON that fixes these errors. Remember:
- campaign_goal must be exactly "awareness", "engagement", or "conversion"
- All required fields must be present: campaign_name, target_audience, key_message, campaign_goal, call_to_action, channel_recommendations
- channel_recommendations must be a list of strings

Respond with valid JSON only. Keep each string value to 1–2 sentences max.
"""

        response = conversation.chat_completion(repair_prompt, temperature=TEMPERATURE)

        print("Repair response:")
        print(response)
        print()

        success, result = validate_json_output(response, CampaignBrief)

        if success:
            print("✓ Repair successful!")
            return result

        last_error = result
        print(f"✗ Still invalid: {last_error}")
        print()
        retries += 1

    raise ValueError(
        f"Could not generate valid campaign brief after {max_retries} attempts. Last error: {last_error}"
    )


def extract_product_info(factsheet, max_retries=3):
    """Extract structured information from product factsheet."""
    conversation = ConversationManager()

    prompt = build_extract_prompt(factsheet)
    response = conversation.chat_completion(prompt, temperature=TEMPERATURE)

    success, result = validate_json_output(response, ExtractedProductInfo)
    if success:
        return result

    retries = 0
    last_error = result

    while retries < max_retries:
        repair_prompt = f"""
The JSON had errors:

{last_error}

Provide corrected JSON matching the required structure.
Respond with JSON only. Keep each string value to 1–2 sentences max.
Use [] for scarcity_factors if none.
"""
        response = conversation.chat_completion(repair_prompt, temperature=TEMPERATURE)

        success, result = validate_json_output(response, ExtractedProductInfo)
        if success:
            return result

        last_error = result
        retries += 1

    raise ValueError(f"Could not extract product info after {max_retries} attempts. Last error: {last_error}")


def generate_campaign_brief_pipeline(factsheet, max_retries=3):
    """Generate campaign brief using multi-step pipeline."""
    print("Step 1: Extracting product information...")
    extracted = extract_product_info(factsheet, max_retries)
    print(f"✓ Extracted info for: {extracted.product_name}")

    print("Step 2: Drafting campaign brief...")
    conversation = ConversationManager()

    prompt = build_draft_prompt(extracted)
    response = conversation.chat_completion(prompt, temperature=TEMPERATURE)

    print("Initial campaign brief response:")
    print(response)
    print()

    success, result = validate_json_output(response, CampaignBrief)
    if success:
        print("✓ Valid campaign brief generated")
        return result

    print("Step 3: Repairing output...")
    retries = 0
    last_error = result

    while retries < max_retries:
        repair_prompt = f"""
The JSON had validation errors:

{last_error}

Provide corrected JSON. Remember:
- campaign_goal must be "awareness", "engagement", or "conversion"
- All required fields must be present
- channel_recommendations must be a list of strings

Respond with JSON only. Keep each string value to 1–2 sentences max.
"""
        response = conversation.chat_completion(repair_prompt, temperature=TEMPERATURE)

        success, result = validate_json_output(response, CampaignBrief)
        if success:
            print("✓ Repair successful")
            return result

        last_error = result
        retries += 1

    raise ValueError(f"Could not generate valid brief after {max_retries} repair attempts. Last error: {last_error}")


if __name__ == "__main__":
    factsheet = """
Product: Limited Edition Geisha Reserve
Origin: Hacienda La Esmeralda, Panama
Altitude: 1,600-1,800 meters
Processing: Natural, 72-hour fermentation
Flavor Profile: Jasmine, bergamot, white peach, honey sweetness,
silky body, complex finish with hints of tropical fruit
Certifications: Single Estate, Competition Grade
Limited Production: Only 500 bags produced this season
Story: This micro-lot scored 94.1 points in the 2024 Cup of Excellence
competition. The beans come from 30-year-old Geisha trees grown in
volcanic soil. The extended fermentation process was developed
specifically for this lot to enhance the floral characteristics.
Price: $89.99/bag
Previous Customer Feedback: "Best coffee I've ever tasted" - Coffee
Review Magazine. Sold out in 3 days last year.
""".strip()

    try:
        brief = generate_campaign_brief_pipeline(factsheet)
        print("✓ Generated valid campaign brief!")
        print(f"Campaign: {brief.campaign_name}")
        print(f"Target: {brief.target_audience}")
        print(f"Goal: {brief.campaign_goal.value}")
        print(f"Channels: {', '.join(brief.channel_recommendations)}")
    except ValueError as e:
        print(f"✗ Failed to generate brief: {e}")
