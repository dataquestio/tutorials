import time
from gitquest import ask_gitquest

# Each query is paired with the chunk_id of the documentation that best answers it
# (its "gold" chunk). recall@5 measures how often that gold chunk survives into the
# final 5 chunks the pipeline sends to the LLM.
TEST_QUERIES = [
    ("In Git, what is git rebase used for?", "5099faa2916858ec"),
    ("What does --value do in the context of git config?", "7de654d26f3b7a26"),
    ("In Git, what is git pull used for?", "51a82ac96bfc04c9"),
    ("In Git, what is git restore used for?", "90eb490de11828d8"),
    ("How do I use git branch correctly in a typical workflow?", "41c0f31dc7394cb1"),
    ("How do I use git pull correctly in a typical workflow?", "f82357cc9be47681"),
    ("What is the difference between git fetch and git pull?", "5c283e97eb292f2e"),
]

# Short pause between pipeline calls. Each ask_gitquest() call makes several
# embedding requests, and firing dozens of them back to back can hit the rate
# limits on a free Cohere trial key. A small delay keeps us comfortably under.
DELAY_BETWEEN_CALLS = 3.0


def run_experiment(k, n_runs=3):
    recalls = []
    total_times = []
    candidate_counts = []

    for query, gold_id in TEST_QUERIES:
        found_count = 0
        query_times = []
        query_candidates = []

        for _ in range(n_runs):
            t0 = time.time()
            result = ask_gitquest(query, n_results=k)
            query_times.append(time.time() - t0)
            query_candidates.append(result["candidate_count"])

            if any(c["chunk_id"] == gold_id for c in result["retrieved_chunks"]):
                found_count += 1

            time.sleep(DELAY_BETWEEN_CALLS)

        # Majority rule: count the gold as "found" only if it showed up in at
        # least 2 of the 3 runs. Retrieval varies slightly from run to run, so a
        # single lucky hit shouldn't count as reliable recall.
        recalls.append(found_count >= 2)
        total_times.append(sum(query_times) / n_runs)
        candidate_counts.append(sum(query_candidates) / n_runs)

    return {
        "k": k,
        "recall": sum(recalls) / len(recalls),
        "per_query": list(zip([q for q, _ in TEST_QUERIES], recalls, candidate_counts)),
        "avg_total": sum(total_times) / len(total_times),
        "avg_candidates": sum(candidate_counts) / len(candidate_counts),
    }


for k in [5, 10, 20]:
    print(f"Running experiment for k={k}...")
    results = run_experiment(k)
    print(f"  Recall@5:        {results['recall']:.0%}")
    print(f"  Avg candidates:  {results['avg_candidates']:.1f}  (pool size before reranking)")
    print(f"  Avg total time:  {results['avg_total']:.2f}s")
    print(f"  Per-query:")
    for query, found, cands in results["per_query"]:
        mark = "found" if found else "MISSING"
        print(f"    [{mark:>7}]  pool~{cands:>4.0f}  {query}")
    print()
