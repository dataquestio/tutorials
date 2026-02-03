from openai import OpenAI
import json
import os
from products import get_product_info, calculate_bulk_price

TOOL_FUNCTIONS = {
    "get_product_info": get_product_info,
    "calculate_bulk_price": calculate_bulk_price
}

def execute_tool(function_name: str, arguments: dict) -> str:
    """Safely execute a tool and return JSON result."""
    if function_name not in TOOL_FUNCTIONS:
        return json.dumps({"error": f"Unknown function: {function_name}"})

    try:
        result = TOOL_FUNCTIONS[function_name](**arguments)
        return json.dumps(result)
    except TypeError as e:
        return json.dumps({"error": f"Invalid arguments: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {e}"})

client = OpenAI(
    api_key=os.environ.get("TOGETHER_API_KEY"),
    base_url="https://api.together.xyz/v1"
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_product_info",
            "description": "Get detailed information about a GlobalJava Roasters product including name, origin, flavor profile, and current price. Use this when a customer asks about a specific product.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product identifier, e.g., 'ethiopian-yirgacheffe', 'house-blend', 'geisha-reserve'"
                    }
                },
                "required": ["product_id"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_bulk_price",
            "description": "Calculate total price for a bulk order with volume discounts. Discounts: 5% for 25+ bags, 10% for 50+ bags, 15% for 100+ bags.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product identifier"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Number of bags to order"
                    }
                },
                "required": ["product_id", "quantity"],
                "additionalProperties": False
            }
        }
    }
]

def run_agent(user_message: str, tools: list, max_iterations: int = 10) -> str:
    """Run the agentic loop until the model produces a final response."""

    messages = [
        {"role": "system", "content": "You are a product assistant for GlobalJava Roasters. Always use the available tools to look up current product information and pricing. Do not rely on general knowledge about coffee."},
        {"role": "user", "content": user_message}
    ]

    for i in range(max_iterations):
        response = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2
        )

        assistant_message = response.choices[0].message

        # No tool calls means we're done
        if not assistant_message.tool_calls:
            return assistant_message.content
        
        messages.append(assistant_message)

        # Process each tool call
        for tool_call in assistant_message.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            print(f"  Tool call: {function_name}({arguments})")
            
            result = execute_tool(function_name, arguments)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result  # Already JSON-serialized by execute_tool
            })

    return "Max iterations reached"

if __name__ == "__main__":
    question = "What is the price of 50 bags of Yirgacheffe?"

    print("User:", question)
    print("\nProcessing...")
    response = run_agent(question, tools)
    print("\nAssistant:", response)