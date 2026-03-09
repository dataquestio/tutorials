import os
import json
import tiktoken
import chromadb
import cohere
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

enc = tiktoken.encoding_for_model("gpt-4o-mini")

def count_tokens(text):
    return len(enc.encode(text))


MAX_REFORMULATIONS = 3

EXPANSION_PROMPT = """You are helping improve search over Git documentation.

Given a user's question, generate 2 or 3 alternative phrasings that use
different vocabulary but ask the same thing. Use terminology that might
appear in official Git documentation (command names, flags, technical terms).

Return ONLY the alternative phrasings, one per line, with no numbering,
no bullet points, no explanation, and no blank lines.

User question: {query}"""


def expand_query(query):
    response = oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": EXPANSION_PROMPT.format(query=query)}],
        temperature=0.3,
    )

    raw = (response.choices[0].message.content or "").strip()
    lines = [line.strip() for line in raw.splitlines() if line.strip()]

    reformulations = []
    for line in lines:
        # Strip common bullet prefixes in case the model ignores "no bullets"
        for prefix in ("- ", "* ", "• "):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break

        # Strip simple numeric prefixes in case the model uses numbering
        if len(line) >= 3 and line[0].isdigit() and line[1] in (".", ")") and line[2] == " ":
            line = line[3:].strip()

        lowered = line.lower()

        # Skip commentary lines if the model adds preamble
        if lowered.startswith(("here are", "alternative", "reformulation", "sure", "note:", "explanation:")):
            continue

        # Skip exact echoes of the original query
        if lowered == query.lower():
            continue

        if line:
            reformulations.append(line)
        if len(reformulations) >= MAX_REFORMULATIONS:
            break

    return reformulations if reformulations else [query]


def expand_and_retrieve(query, n_results=10):
    reformulations = expand_query(query)
    all_queries = [query] + reformulations
    seen = {}
    for q in all_queries:
        for chunk in retrieve(q, n_results=n_results):
            cid = chunk["chunk_id"]
            if cid not in seen or chunk["distance"] < seen[cid]["distance"]:
                seen[cid] = chunk
    return sorted(seen.values(), key=lambda x: x["distance"])


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
    parts = []
    for chunk in chunks:
        parts.append(
            f"chunk_id: {chunk['chunk_id']}\n"
            f"title: {chunk['title']}\n"
            f"source_type: {chunk['source_type']}\n"
            f"command: {chunk['command']}\n\n"
            f"{chunk['text']}"
        )
    return "\n\n---\n\n".join(parts)


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


def rerank(query, chunks, top_n=5):
    documents = [c["text"] for c in chunks]
    response = co.rerank(
        model="rerank-v3.5",
        query=query,
        documents=documents,
        top_n=top_n
    )
    reranked = []
    for result in response.results:
        chunk = chunks[result.index]
        reranked.append({
            **chunk,
            "rerank_score": result.relevance_score
        })
    return reranked


def select_chunks_within_budget(chunks, token_budget=6000):
    selected = []
    used = 0
    for chunk in chunks:
        chunk_tokens = count_tokens(build_context([chunk]))
        if used + chunk_tokens <= token_budget:
            selected.append(chunk)
            used += chunk_tokens
        else:
            continue
    return selected


def ask_gitquest(query, n_results=10, token_budget=6000):
    # Step 1: expand query and retrieve candidate set
    candidates = expand_and_retrieve(query, n_results=n_results)

    # Step 2: rerank candidates
    reranked = rerank(query, candidates, top_n=5)

    # Step 3: apply token budget as a safety net
    final_chunks = select_chunks_within_budget(reranked, token_budget=token_budget)

    # Step 4: build context and generate
    context = build_context(final_chunks)
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
    citations = parse_citations(raw_answer, final_chunks)
    answer_text = raw_answer.split("SOURCES:")[0].strip()

    return {
        "query": query,
        "answer": answer_text,
        "citations": citations,
        "retrieved_chunks": final_chunks,
        "candidate_count": len(candidates)
    }
