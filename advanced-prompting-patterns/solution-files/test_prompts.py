from campaign_generator import generate_campaign_brief
from models import CampaignGoal

def test_basic_generation():
    """Can we generate a valid brief at all?"""
    factsheet = """
    Product: House Blend Medium Roast
    Origin: Colombia and Brazil blend
    Flavor: Balanced, chocolatey, nutty
    Price: $12.99/bag
    """

    brief = generate_campaign_brief(factsheet)

    assert brief.campaign_name, "Campaign name missing"
    assert len(brief.campaign_name) >= 5, "Campaign name too short"
    assert brief.target_audience, "Target audience missing"
    assert brief.campaign_goal in CampaignGoal, "Invalid campaign goal"
    assert len(brief.channel_recommendations) > 0, "No channels recommended"

    print("✓ Basic generation test passed")

def test_premium_product_targeting():
    """Premium products should target sophisticated audiences."""
    factsheet = """
    Product: Single Origin Ethiopian Yirgacheffe
    Origin: Gedeb region, Ethiopia
    Processing: Washed
    Flavor: Floral, citrus, tea-like
    Certifications: Organic, Fair Trade
    Price: $24.99/bag
    """

    brief = generate_campaign_brief(factsheet)

    target = brief.target_audience.lower()
    sophisticated_terms = ['enthusiast', 'connoisseur', 'specialty', 'premium', 'aficionado']

    assert any(term in target for term in sophisticated_terms), \
        f"Premium product should target sophisticated audience, got: {brief.target_audience}"

    print("✓ Premium targeting test passed")

if __name__ == "__main__":
    print("Running prompt tests...\n")
    test_basic_generation()
    test_premium_product_targeting()
    print("\n✓ All tests passed!")
