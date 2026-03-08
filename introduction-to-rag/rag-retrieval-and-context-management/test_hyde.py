import os
import cohere
from openai import OpenAI
from dotenv import load_dotenv

# Import components from gitquest.py
from gitquest import corpus, collection

load_dotenv()

co = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))
oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

HYDE_PROMPT = """You are a technical writer for Git documentation.

Write a short documentation snippet (3-5 sentences) that directly answers
the following question. Write in the style of an official Git manpage or
user manual: technical, precise, using correct Git terminology and command
names. Include the relevant command syntax.

Question: {query}

Documentation snippet:"""

def generate_hypothetical_doc(query):
    response = oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": HYDE_PROMPT.format(query=query)}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

def hyde_retrieve(query, n_results=20):
    hypothetical_doc = generate_hypothetical_doc(query)

    # Embed as a document, not a query, so it lands in the same
    # part of the vector space as the actual corpus chunks
    response = co.embed(
        texts=[hypothetical_doc],
        model="embed-v4.0",
        input_type="search_document",
        embedding_types=["float"]
    )
    embedding = response.embeddings.float[0]

    results = collection.query(
        query_embeddings=[embedding],
        n_results=n_results
    )

    chunks = []
    for chunk_id, metadata, distance in zip(
        results["ids"][0],
        results["metadatas"][0],
        results["distances"][0]
    ):
        chunk = corpus[chunk_id]
        chunks.append({
            "chunk_id": chunk_id,
            "text": chunk["text"],
            "distance": distance,
            "title": chunk["title"],
            "command": metadata["command"],
            "source_type": metadata["source_type"]
        })
    return hypothetical_doc, chunks

# Add your test code below this line
