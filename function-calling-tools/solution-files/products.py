# products.py
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

def get_product_info(product_id: str) -> dict:
    """Look up product information by ID."""
    if product_id not in PRODUCTS:
        return {"error": f"Product '{product_id}' not found"}
    return PRODUCTS[product_id]

from decimal import Decimal

def calculate_bulk_price(product_id: str, quantity: int) -> dict:
    """Calculate price with volume discounts."""
    if product_id not in PRODUCTS:
        return {"error": f"Product '{product_id}' not found"}

    base_price = Decimal(str(PRODUCTS[product_id]["price"]))

    # Apply volume discounts
    if quantity >= 100:
        discount = Decimal("0.15")
    elif quantity >= 50:
        discount = Decimal("0.10")
    elif quantity >= 25:
        discount = Decimal("0.05")
    else:
        discount = Decimal("0")

    unit_price = base_price * (Decimal("1") - discount)
    total_price = unit_price * quantity

    return {
        "quantity": quantity,
        "discount_percent": discount * 100,
        "unit_price": unit_price,
        "total_price": total_price
    }