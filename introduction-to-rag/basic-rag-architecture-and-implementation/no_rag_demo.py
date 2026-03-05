import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

question = "How do I discard all the changes I made to a file and restore it to the last commit?"

response = oai.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "system",
            "content": "You are a helpful Git assistant. Answer concisely."
        },
        {
            "role": "user",
            "content": question
        }
    ]
)

print("Question:", question, "\n")
print("GPT-4o-mini answer (no RAG):")
print(response.choices[0].message.content)
