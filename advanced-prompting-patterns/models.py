from pydantic import BaseModel
from typing import List
from enum import Enum

class CampaignGoal(str, Enum):
    AWARENESS = "awareness"
    ENGAGEMENT = "engagement"
    CONVERSION = "conversion"

class CampaignBrief(BaseModel):
    campaign_name: str
    target_audience: str
    key_message: str
    campaign_goal: CampaignGoal
    call_to_action: str
    channel_recommendations: List[str]

class ExtractedProductInfo(BaseModel):
    product_name: str
    origin_story: str
    unique_features: List[str]
    flavor_highlights: List[str]
    certifications: List[str]
    price_point: str
    scarcity_factors: List[str] = []