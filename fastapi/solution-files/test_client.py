import requests

response = requests.post(
    "http://127.0.0.1:8000/optimize",
    json={
        "prompt": "Write about dogs",
        "goal": "Generate an engaging blog post introduction that hooks readers"
    }
)

print(f"Status: {response.status_code}")
print(f"Response:\n{response.json()}")

bad_response = requests.post(
    "http://127.0.0.1:8000/optimize",
    json={"prompt": "Write about dogs"}  # Missing 'goal'
)

print(f"Status: {bad_response.status_code}")
print(f"Error: {bad_response.json()}")

extra_response = requests.post(
    "http://127.0.0.1:8000/optimize",
    json={
        "prompt": "Write about dogs",
        "goal": "Blog intro",
        "surprise": "extra field"
    }
)

print(f"Status: {extra_response.status_code}")
print(f"Error: {extra_response.json()}")