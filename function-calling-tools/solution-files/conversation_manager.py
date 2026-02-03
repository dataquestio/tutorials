import os
import tiktoken
import json
from openai import OpenAI
from datetime import datetime

DEFAULT_API_KEY = os.environ.get("TOGETHER_API_KEY")
DEFAULT_BASE_URL = "https://api.together.xyz/v1"
DEFAULT_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct-Lite" # Link to models: https://api.together.ai/models
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 350
DEFAULT_TOKEN_BUDGET = 4096


class ConversationManager:
    def __init__(self, api_key=None, base_url=None, model=None, history_file=None, temperature=None, max_tokens=None, token_budget=None):
        if not api_key:
            api_key = DEFAULT_API_KEY
            if not api_key:
                raise ValueError(
                    "TOGETHER_API_KEY environment variable is not set. "
                    "Please set it or pass an api_key directly to ConversationManager."
                )
        if not base_url:
            base_url = DEFAULT_BASE_URL
            
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        if history_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.history_file = f"conversation_history_{timestamp}.json"
        else:
            self.history_file = history_file

        self.model = model if model else DEFAULT_MODEL
        self.temperature = temperature if temperature else DEFAULT_TEMPERATURE
        self.max_tokens = max_tokens if max_tokens else DEFAULT_MAX_TOKENS
        self.token_budget = token_budget if token_budget else DEFAULT_TOKEN_BUDGET

        self.system_messages = {
            "blogger": "You are a creative blogger specializing in engaging and informative content for GlobalJava Roasters.",
            "social_media_expert": "You are a social media expert, crafting catchy and shareable posts for GlobalJava Roasters.",
            "creative_assistant": "You are a creative assistant skilled in crafting engaging marketing content for GlobalJava Roasters.",
            "custom": "Enter your custom system message here."
        }
        self.system_message = self.system_messages["creative_assistant"]
        self.conversation_history = [{"role": "system", "content": self.get_system_message()}]

    def count_tokens(self, text):
        try:
            encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")

        tokens = encoding.encode(text)
        return len(tokens)

    def total_tokens_used(self):
        return sum(self.count_tokens(message['content']) for message in self.conversation_history)
    
    def enforce_token_budget(self):
        while self.total_tokens_used() > self.token_budget:
            if len(self.conversation_history) <= 1:
                break
            self.conversation_history.pop(1)

    def set_persona(self, persona):
        if persona in self.system_messages:
            self.system_message = self.system_messages[persona]
            self.update_system_message_in_history()
        else:
            raise ValueError(f"Unknown persona: {persona}. Available personas are: {list(self.system_messages.keys())}")

    def set_custom_system_message(self, custom_message):
        if not custom_message:
            raise ValueError("Custom message cannot be empty.")
        self.system_messages['custom'] = custom_message
        self.set_persona('custom')
    
    def get_system_message(self):
        system_message = self.system_message
        system_message += f"\nImportant: Tailor your response to fit within {DEFAULT_MAX_TOKENS/2} word limit\n"
        return system_message        

    def update_system_message_in_history(self):
        if self.conversation_history and self.conversation_history[0]["role"] == "system":
            self.conversation_history[0]["content"] = self.get_system_message()
        else:
            system_message = self.system_message
            system_message += f"\nImportant: Tailor your response to fit within {DEFAULT_MAX_TOKENS/2} words limit\n"
            self.conversation_history.insert(0, {"role": "system", "content": self.get_system_message()})

    def chat_completion(self, prompt, temperature=None, max_tokens=None):
        temperature = temperature if temperature is not None else self.temperature
        max_tokens = max_tokens if max_tokens is not None else self.max_tokens

        self.conversation_history.append({"role": "user", "content": prompt})

        self.enforce_token_budget()

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation_history,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            print(f"An error occurred while generating a response: {e}")
            return None

        ai_response = response.choices[0].message.content
        self.conversation_history.append({"role": "assistant", "content": ai_response})

        return ai_response
    
    def reset_conversation_history(self):
        self.conversation_history = [{"role": "system", "content": self.get_system_message()}]

        
