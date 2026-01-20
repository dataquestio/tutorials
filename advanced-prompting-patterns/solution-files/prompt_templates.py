CAMPAIGN_SYSTEM_V2 = """
PROMPT_ID: campaign_brief_generator
VERSION: 2.0
LAST_UPDATED: 2026-01-08
CHANGELOG:
- v2.0: Added specific channel guidance for premium products
- v1.1: Clarified target audience requirements
- v1.0: Initial version

You are a marketing campaign strategist for GlobalJava Roasters,
a premium coffee company focused on quality and sustainability.
"""

CAMPAIGN_SYSTEM = """
You are a marketing campaign strategist for GlobalJava Roasters,
a premium coffee company focused on quality and sustainability.
"""

CAMPAIGN_TASK = """
Create a marketing campaign brief for the product described below.
"""

CAMPAIGN_CONSTRAINTS = """
Follow these rules:
- Base all claims on the provided product information
- Use professional but engaging language appropriate for coffee enthusiasts
- Focus on the product's unique characteristics and value proposition
- Recommend marketing channels suitable for premium coffee consumers
"""

CAMPAIGN_OUTPUT = """
Output your response as valid JSON with this structure:

{{
  "campaign_name": "string",
  "target_audience": "string",
  "key_message": "string",
  "campaign_goal": "awareness" | "engagement" | "conversion",
  "call_to_action": "string",
  "channel_recommendations": ["string", "string", ...]
}}

Respond with JSON only. No explanations or markdown. Keep each string value to 1–2 sentences max.
"""

def build_campaign_prompt(factsheet):
    """Build a campaign brief prompt from template blocks."""
    reference = f"Product Information:\n{factsheet}"

    return f"""
{CAMPAIGN_SYSTEM}

{CAMPAIGN_TASK}

{CAMPAIGN_CONSTRAINTS}

{reference}

{CAMPAIGN_OUTPUT}
""".strip()

EXTRACT_SYSTEM = "You are a data extraction specialist."

EXTRACT_TASK = """
Extract key marketing-relevant information from the product factsheet below.
Focus on facts that would matter for a marketing campaign.
"""

EXTRACT_OUTPUT = """
Output JSON with this structure:
{{
  "product_name": "string",
  "origin_story": "string",
  "unique_features": ["string", "string", ...],
  "flavor_highlights": ["string", "string", ...],
  "certifications": ["string", "string", ...],
  "price_point": "budget" | "mid-range" | "premium" | "luxury",
  "scarcity_factors": ["string", ...] // use [] if none
}}

Respond with JSON only.
"""

def build_extract_prompt(factsheet):
    reference = f"Product Factsheet:\n{factsheet}"
    return f"""
{EXTRACT_SYSTEM}

{EXTRACT_TASK}

{reference}

{EXTRACT_OUTPUT}
""".strip()


DRAFT_CAMPAIGN_SYSTEM = """
You are a marketing campaign strategist for GlobalJava Roasters.
"""

DRAFT_CAMPAIGN_TASK = """
Create a compelling marketing campaign brief using the extracted
product information provided below.
"""

DRAFT_CAMPAIGN_CONSTRAINTS = """
Guidelines:
- Craft a campaign name that captures the product's essence
- Target audience should reflect the price point and product characteristics
- Key message should highlight the most compelling unique features
- Choose an appropriate campaign goal based on product positioning
- Create a clear, actionable call-to-action
- Recommend channels that reach premium coffee enthusiasts
"""

def build_draft_prompt(extracted_info):
    # Format the extracted info nicely
    info_text = f"""
Product: {extracted_info.product_name}
Origin Story: {extracted_info.origin_story}
Unique Features: {', '.join(extracted_info.unique_features)}
Flavor Highlights: {', '.join(extracted_info.flavor_highlights)}
Price Point: {extracted_info.price_point}
"""
    if extracted_info.scarcity_factors:
        info_text += f"Scarcity: {', '.join(extracted_info.scarcity_factors)}\n"

    return f"""
{DRAFT_CAMPAIGN_SYSTEM}

{DRAFT_CAMPAIGN_TASK}

{DRAFT_CAMPAIGN_CONSTRAINTS}

Extracted Product Information:
{info_text}

{CAMPAIGN_OUTPUT}
""".strip()