from openai import OpenAI
import json
import os
from product_server import mcp

client = OpenAI(
    api_key=os.environ.get("TOGETHER_API_KEY"),
    base_url="https://api.together.xyz/v1"
)

def get_openai_tools(mcp_server):
    """Convert MCP tools to OpenAI tools format."""
    tools = []

    for tool in mcp_server._tool_manager._tools.values():
        tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "strict": True,
                "parameters": tool.parameters
            }
        })

    return tools

def get_tool_functions(mcp_server):
    """Get a mapping of tool names to their functions."""
    return {name: tool.fn for name, tool in mcp_server._tool_manager._tools.items()}

def run_agent(user_message: str, mcp_server, max_iterations: int = 10) -> str:
    """Run the agentic loop using tools from an MCP server."""

    # Convert MCP tools to OpenAI format
    tools = get_openai_tools(mcp_server)
    tool_functions = get_tool_functions(mcp_server)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a product assistant for GlobalJava Roasters. "
                "Always use the available tools to look up current product information and pricing. "
                "Do not rely on general knowledge about coffee."
            )
        },
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

        if not assistant_message.tool_calls:
            return assistant_message.content

        messages.append(assistant_message)

        for tool_call in assistant_message.tool_calls:
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            print(f"  Tool call: {function_name}({arguments})")

            result = tool_functions[function_name](**arguments)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })

    return "Max iterations reached"

if __name__ == "__main__":
    question = "What is the price of 50 bags of Yirgacheffe?"

    print("User:", question)
    print("\nProcessing...")
    response = run_agent(question, mcp)
    print("\nAssistant:", response)

# Single-tool query
run_agent("Tell me about the Geisha Reserve", mcp)

# Different bulk quantity
run_agent("How much for 100 bags of house blend?", mcp)