import os
import tiktoken
import json
from openai import OpenAI
from datetime import datetime

DEFAULT_API_KEY = os.environ.get("TOGETHER_API_KEY")
DEFAULT_BASE_URL = "https://api.together.xyz/v1"
DEFAULT_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct-Lite"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 350
DEFAULT_TOKEN_BUDGET = 4096


class ConversationManager:
    def __init__(self, api_key=None, base_url=None, model=None, history_file=None, temperature=None, max_tokens=None, token_budget=None):
        if not api_key:
            api_key = DEFAULT_API_KEY
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
        self.conversation_history = [{"role": "system", "content": self.self.get_system_message()}]

        
section_one = """

European Union (EU) imports are dominated by unroasted green coffee beans, which accounts for about 90 percent of trade. Top suppliers in 2022/23 (October through September) included Brazil (32 percent), Vietnam (26 percent), Uganda (7 percent), and Honduras (6 percent). Imports reached a record 49.1 million bags the previous year but slipped 2.6 million bags this year as lower imports from Brazil more than offset gains from Vietnam. These two countries accounted for 54 to 58 percent of EU green coffee imports over the last 10 years, leaving limited market share for other suppliers. During this same period, Uganda gained 1.2 million bags to total 3.4 million on rising production while Colombia lost 500,000 bags to total 1.8 million on falling output. 

EU imports of roasted coffee totaled just 1.4 million bags in 2022/23, down from a record 2.1 million bags 4 years earlier on reduced imports from Switzerland. Top suppliers included Switzerland (77 percent) and the United Kingdom (13 percent). Because coffee beans begin to lose flavor and aroma shortly after being roasted, these imports are mostly limited to neighboring non-producing countries

Imports of soluble coffee rebounded 300,000 bags to 3.7 million in 2022/23. Top suppliers included the United Kingdom (34 percent), Vietnam (12 percent), India (12 percent), and Ecuador (10 percent). While imports from the United Kingdom have been nearly flat at 1.3 million bags for a decade, imports from India and Vietnam gained about 300,000 bags to each total over 400,000.

EU green coffee imports are forecast to rebound slightly in 2023/24 to 47.0 million bags primarily due to stronger shipments from Brazil, while roasted and soluble coffee imports remain flat at 1.4 million bags and 3.7 million bags, respectively.
"""

section_two = """
2023/24 Coffee Overview
World coffee production for 2023/24 is
forecast to reach 171.4 million bags (60
kilograms), 6.9 million bags higher than
the previous year. Higher output in
Brazil, Colombia, and Ethiopia is
expected to more than offset reduced
production in Indonesia. Global coffee
bean exports are expected up 8.4
million bags to 119.9 million, primarily
on strong shipments from Brazil. With
global consumption forecast at a record
169.5 million bags, ending inventories
are expected to continue to tighten to a
12-year low of 26.5 million bags.
Brazil combined Arabica and Robusta
harvest is forecast up 3.7 million bags to
66.3 million in 2023/24. Arabica output
is forecast to improve 5.1 million bags
to 44.9 million. In January 2023, coffee
trees in top growing region Minas
Gerais experienced higher than average
rains during the fruit development
stage, causing difficulties for some
growers in controlling plant diseases
and pests. However, increased
precipitation resulted in coarser and
heavier beans compared to the last
crop, which contributed to production
gains. Although output is expected to
expand, this quantity is below previous
crops that peaked at nearly 50.0 million bags. Arabica trees in many growing regions continue to recover
from severe weather that occurred in 2021 including severe frosts, high temperatures, and below-
average rainfall that lowered production in 2021/22 and 2022/23. Following 6 years of expansion, the
Robusta harvest is forecast to decline 1.4 million bags to 21.4 million as reduced precipitation and cooler
temperatures leading up to the flowering stage lowered yields in Espirito Santo, where the vast majority
is grown. Coffee bean exports are forecast to rebound 7.3 million bags to 39.5 million, fueled by higher
supplies and stronger EU and U.S. import demand.
Vietnam production is forecast to add 300,000 bags to reach 27.5 million. Cultivated area is forecast
unchanged, with nearly 95 percent of total output remaining as Robusta. However, with lower total
supplies due to last year’s stocks drawdown, bean exports are forecast to decline 2.4 million bags to
23.0 million.
Colombia Arabica production is forecast up 800,000 bags to 11.5 million on slightly higher yields.
However, yields remain nearly 15 percent below normal because growers limited fertilizer use due to
high prices. Bean exports, mostly to the United States and EU, are forecast up 1.2 million bags to 10.8
million on strong demand.
Indonesia combined Arabica and
Robusta harvest is forecast down 2.2
million bags to 9.7 million. Robusta
production is expected to drop 2.1
million bags to 8.4 million. Excessive
rain during cherry development lowered
yields and caused sub-optimal
conditions for pollination in the lowland
areas of Southern Sumatra and Java,
where approximately 75 percent of
coffee is grown. Arabica production is
seen dipping slightly to 1.3 million bags.
Bean exports are forecast to plummet
2.7 million bags to 5.0 million on sharply
reduced supplies.
India combined Arabica and Robusta harvest is forecast nearly unchanged at 6.0 million bags. Arabica
production is forecast to drop 200,000 bags to 1.4 million due primarily to a prolonged dry spell from
December 2022 to March 2023 which was followed by poor pre-monsoon rains. Robusta production is
expected to rise 300,000 bags to 4.5 million on slightly higher yields. Bean exports are forecast up
300,000 bags to 4.3 million on a slight inventory drawdown.
"""

section_three = """
Revisions to 2022/23 Forecasts
World production is lowered 5.5 million bags from the June 2023 estimate to 164.5 million.
• Vietnam is 2.6 million bags lower to 27.2 million due to dry conditions that dropped yields.
• Ethiopia is reduced 1.0 million bags to 7.3 million as dry conditions lowered yields.
• Colombia is down 600,000 bags to 10.7 million as damaging rains fell in some areas during the
flowering period.
World bean exports are lowered 4.9 million bags to 111.6 million.
• Colombia is down 1.2 million bags to 9.6 million on lower output and higher ending stocks.
• Ethiopia is lowered 900,000 bags to 3.9 million on reduced output.
• Vietnam is reduced 600,000 bags to 25.4 million on lower output.
World ending stocks are revised down 4.0 million bags to 27.6 million.
• EU is down 3.3 million bags to 9.3 million on stronger-than-anticipated consumption.
• Vietnam is lowered 1.4 million bags to 300,000 on reduced production
"""

section_one_summary = f"""
Section One Summary:
 Here's a summary of the key points from the ICO coffee report on EU's coffee import trends:

- The European Union is the world's largest coffee importer, mainly of unroasted green coffee beans, making up approximately 90% of their coffee trade.
- In the 2022/23 period, the leading suppliers of green coffee to the EU were Brazil (32%), Vietnam (26%), Uganda (7%), and Honduras (6%).
- EU's green coffee imports decreased by 2.6 million bags from the previous year's record of 49.1 million bags, primarily due to reduced imports from Brazil.
- Over the past decade, Brazil and Vietnam have consistently provided between 54% and 58% of the EU's green coffee imports, with other suppliers having a limited market share.
- Uganda's exports to the EU increased by 1.2 million bags due to higher production, while Colombia's exports decreased by 500,000 bags due to lower output.
- Roasted coffee imports in the EU dropped to 1.4 million bags in 2022/23, with the main suppliers being Switzerland (77%) and the United Kingdom (13%).
- Soluble coffee imports to the EU rose to 3.7 million bags, with the UK, Vietnam, India, and Ecuador being the primary suppliers.
- Green coffee imports are expected to slightly increase in 2023/24, with a forecast of 47.0 million bags, mainly due to expected higher shipments from Brazil.
- Imports of roasted and soluble coffee are predicted to remain stable at 1.4 million bags and 3.7 million bags, respectively.

This summary encapsulates the major trends and projections regarding the European Union's coffee import habits as detailed in the ICO report.
"""

section_two_summary = f"""
Section Two Summary:
 Here's a summary of the 2023/24 Coffee Overview from the ICO report:

- Global coffee production is forecast to rise to 171.4 million bags, an increase of 6.9 million bags from the previous year.
- Brazil, Colombia, and Ethiopia are expected to see higher outputs, compensating for a production decline in Indonesia.
- Worldwide coffee bean exports are projected to increase by 8.4 million bags to 119.9 million, largely driven by exports from Brazil.
- Consumption is forecast to hit a record 169.5 million bags, leading to the lowest ending inventories in 12 years, at 26.5 million bags.
- Brazil's total coffee harvest is expected to rise by 3.7 million bags to 66.3 million, with Arabica production up by 5.1 million bags despite previous weather challenges.
- Robusta production in Brazil is forecast to decrease by 1.4 million bags due to less favorable weather conditions.
- Brazil's coffee bean exports are expected to surge by 7.3 million bags to 39.5 million because of increased supply and demand from the EU and U.S.
- Vietnam's production is forecast to increase by 300,000 bags to 27.5 million, though exports may drop due to depleted stocks from the previous year.
- Colombia is anticipated to see an 800,000 bag increase in Arabica production, with exports growing due to strong demand.
- Indonesia's coffee harvest is projected to fall by 2.2 million bags, with exports expected to significantly decline.
- India's coffee harvest is expected to remain stable at 6.0 million bags, with a slight increase in Robusta offsetting a decrease in Arabica production. Exports are predicted to rise marginally.

This summary encapsulates the projected trends and changes in coffee production, export, and consumption for the 2023/24 period as reported by the ICO.
"""