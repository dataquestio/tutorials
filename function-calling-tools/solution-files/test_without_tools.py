from conversation_manager import ConversationManager

conversation = ConversationManager()

prompt = """
You are a helpful product assistant for GlobalJava Roasters.

Customer question: What's the current price for our Ethiopian Yirgacheffe and how much does it cost for a 50-bag order?

Respond with the product information.
"""

response = conversation.chat_completion(prompt)
print(response)