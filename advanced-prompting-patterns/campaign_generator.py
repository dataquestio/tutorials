from conversation_manager import ConversationManager
from prompt_templates import build_campaign_prompt, build_extract_prompt, build_draft_prompt
from models import CampaignBrief, ExtractedProductInfo
from utils import validate_json_output

def generate_campaign_brief(factsheet, max_retries=3):
    """Generate a validated campaign brief with automatic repair."""

    conversation = ConversationManager()

    # Use the template builder
    initial_prompt = build_campaign_prompt(factsheet)

    response = conversation.chat_completion(initial_prompt)

    print("Initial response:")
    print(response)
    print()

    success, result = validate_json_output(response, CampaignBrief)

    # If valid on first try, return it
    if success:
        print("✓ Valid on first attempt!")
        return result

    # Otherwise, try to repair
    print(f"✗ Validation failed: {result}")
    print()
    
    retries = 0
    while retries < max_retries:
        print(f"Attempting repair {retries + 1}/{max_retries}...")
        
        repair_prompt = f"""
The JSON you provided had validation errors:

{result}

Please provide corrected JSON that fixes these errors. Remember:
- campaign_goal must be exactly "awareness", "engagement", or "conversion"
- All required fields must be present: campaign_name, target_audience, key_message, campaign_goal, call_to_action, channel_recommendations
- channel_recommendations must be a list of strings

Respond with valid JSON only.
"""

        response = conversation.chat_completion(repair_prompt)
        print("Repair response:")
        print(response)
        print()
        
        success, result = validate_json_output(response, CampaignBrief)

        if success:
            print("✓ Repair successful!")
            return result
        
        print(f"✗ Still invalid: {result}")
        print()
        retries += 1

    # If we exhausted retries, raise an error
    raise ValueError(f"Could not generate valid campaign brief after {max_retries} attempts. Last error: {result}")

def extract_product_info(factsheet, max_retries=3):
    """Extract structured information from product factsheet."""
    conversation = ConversationManager()

    prompt = build_extract_prompt(factsheet)
    response = conversation.chat_completion(prompt)
    success, result = validate_json_output(response, ExtractedProductInfo)

    if success:
        return result

    # Simple repair loop (same pattern as before)
    retries = 0
    while retries < max_retries:
        repair_prompt = f"The JSON had errors: {result}\n\nProvide corrected JSON matching the required structure."
        response = conversation.chat_completion(repair_prompt)
        success, result = validate_json_output(response, ExtractedProductInfo)
        if success:
            return result
        retries += 1

    raise ValueError(f"Could not extract product info after {max_retries} attempts")

def generate_campaign_brief_pipeline(factsheet, max_retries=3):
    """Generate campaign brief using multi-step pipeline."""

    # Step 1: Extract structured information
    print("Step 1: Extracting product information...")
    extracted = extract_product_info(factsheet, max_retries)
    print(f"✓ Extracted info for: {extracted.product_name}")

    # Step 2: Draft campaign brief
    print("Step 2: Drafting campaign brief...")
    conversation = ConversationManager()

    prompt = build_draft_prompt(extracted)
    response = conversation.chat_completion(prompt)

    print("Initial campaign brief response:")
    print(response)
    print()

    success, result = validate_json_output(response, CampaignBrief)

    if success:
        print("✓ Valid campaign brief generated")
        return result

    # Step 3: Repair if needed
    print("Step 3: Repairing output...")
    retries = 0
    while retries < max_retries:
        repair_prompt = f"""
The JSON had validation errors:

{result}

Provide corrected JSON. Remember:
- campaign_goal must be "awareness", "engagement", or "conversion"
- All required fields must be present
- channel_recommendations must be a list of strings

Respond with JSON only.
"""
        response = conversation.chat_completion(repair_prompt)
        success, result = validate_json_output(response, CampaignBrief)

        if success:
            print("✓ Repair successful")
            return result
        retries += 1

    raise ValueError(f"Could not generate valid brief after {max_retries} repair attempts")

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
"""

try:
    brief = generate_campaign_brief_pipeline(factsheet)
    print("✓ Generated valid campaign brief!")
    print(f"Campaign: {brief.campaign_name}")
    print(f"Target: {brief.target_audience}")
    print(f"Goal: {brief.campaign_goal.value}")
    print(f"Channels: {', '.join(brief.channel_recommendations)}")
except ValueError as e:
    print(f"✗ Failed to generate brief: {e}")
