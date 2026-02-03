from fastmcp import FastMCP
from decimal import Decimal

# Initialize the MCP server
mcp = FastMCP("GlobalJava Product Tools")

PRODUCTS = {
    "ethiopian-yirgacheffe": {
        "name": "Ethiopian Yirgacheffe Single-Origin",
        "origin": "Yirgacheffe region, Ethiopia",
        "flavor_profile": "Bright citrus, floral aroma, light body",
        "price": 18.99,
        "certifications": ["Fair Trade", "Organic"]
    },
    "house-blend": {
        "name": "GlobalJava House Blend",
        "origin": "Colombia and Brazil blend",
        "flavor_profile": "Balanced, chocolatey, nutty",
        "price": 12.99,
        "certifications": []
    },
    "geisha-reserve": {
        "name": "Limited Edition Geisha Reserve",
        "origin": "Hacienda La Esmeralda, Panama",
        "flavor_profile": "Jasmine, bergamot, white peach",
        "price": 89.99,
        "certifications": ["Single Estate", "Competition Grade"]
    }
}

@mcp.tool()
def get_product_info(product_id: str) -> dict:
    """Get detailed information about a GlobalJava Roasters product including
    name, origin, flavor profile, and current price. Use this when a customer
    asks about a specific product.

    Args:
        product_id: The product identifier, e.g., 'ethiopian-yirgacheffe', 'house-blend'
    """
    if product_id not in PRODUCTS:
        return {"error": f"Product '{product_id}' not found"}
    return PRODUCTS[product_id]

@mcp.tool()
def calculate_bulk_price(product_id: str, quantity: int) -> dict:
    """Calculate total price for a bulk order with volume discounts.
    Discounts: 5% for 25+ bags, 10% for 50+ bags, 15% for 100+ bags.

    Args:
        product_id: The product identifier
        quantity: Number of bags to order
    """
    if product_id not in PRODUCTS:
        return {"error": f"Product '{product_id}' not found"}

    base_price = Decimal(str(PRODUCTS[product_id]["price"]))

    if quantity >= 100:
        discount = Decimal("0.15")
    elif quantity >= 50:
        discount = Decimal("0.10")
    elif quantity >= 25:
        discount = Decimal("0.05")
    else:
        discount = Decimal("0")

    unit_price = base_price * (1 - discount)
    total_price = unit_price * quantity

    return {
        "quantity": quantity,
        "discount_percent": float(discount * 100),
        "unit_price": float(unit_price),
        "total_price": float(total_price)
    }