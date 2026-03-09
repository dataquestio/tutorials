import os
import json
import chromadb
import cohere
import tiktoken
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

co = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))
oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
client = chromadb.PersistentClient(path="data/chroma_scoped")
collection = client.get_collection(name="git_docs_scoped")

corpus = {}
with open("data/git_kb_corpus_scoped/corpus.jsonl", "r") as f:
    for line in f:
        chunk = json.loads(line)
        corpus[chunk["chunk_id"]] = chunk


def retrieve(query, n_results=5):
    response = co.embed(
        texts=[query],
        model="embed-v4.0",
        input_type="search_query",
        embedding_types=["float"]
    )
    query_embedding = response.embeddings.float[0]
    results = collection.query(
        query_embeddings=[query_embedding],
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
            "title": chunk["title"],
            "source_type": metadata["source_type"],
            "command": metadata["command"],
            "distance": distance
        })
    return chunks


def build_context(chunks):
    context_parts = []
    for i, chunk in enumerate(chunks, start=1):
        context_parts.append(
            f"[SOURCE {i}]\n"
            f"chunk_id: {chunk['chunk_id']}\n"
            f"title: {chunk['title']}\n"
            f"source_type: {chunk['source_type']}\n"
            f"command: {chunk['command']}\n\n"
            f"{chunk['text']}"
        )
    return "\n\n---\n\n".join(context_parts)


SYSTEM_PROMPT = """You are GitQuest, a Git support agent that helps \
developers use Git correctly and confidently.

Answer the user's question using ONLY the documentation provided below. \
Do not use knowledge from your training data.

Guidelines:
- Provide the exact command syntax as shown in the documentation
- Briefly explain what the command does and why it works
- If there are important options or variations shown in the docs, mention them
- If the provided documentation does not contain enough information to \
answer the question, say so explicitly rather than guessing or drawing \
on outside knowledge

End your answer with a SOURCES section listing only the chunk_ids you \
drew from, in this exact format:

SOURCES:
- chunk_id: <id> | <title>

Documentation:
{context}"""


def parse_citations(raw_answer, retrieved_chunks):
    valid_ids = {c["chunk_id"] for c in retrieved_chunks}
    cited = []
    if "SOURCES:" in raw_answer:
        sources_section = raw_answer.split("SOURCES:")[1]
        for line in sources_section.strip().split("\n"):
            if "chunk_id:" in line:
                cited_id = line.split("chunk_id:")[1].split("|")[0].strip()
                if cited_id in valid_ids:
                    chunk = corpus[cited_id]
                    cited.append({
                        "chunk_id": cited_id,
                        "title": chunk["title"],
                        "command": chunk["command"],
                        "source_type": chunk["source_type"]
                    })
    return cited


def ask_gitquest(query, n_results=5):
    chunks = retrieve(query, n_results=n_results)
    context = build_context(chunks)
    response = oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(context=context)
            },
            {"role": "user", "content": query}
        ]
    )
    raw_answer = response.choices[0].message.content
    citations = parse_citations(raw_answer, chunks)
    answer_text = raw_answer.split("SOURCES:")[0].strip()

    return {
        "query": query,
        "answer": answer_text,
        "citations": citations,
        "retrieved_chunks": chunks
    }
