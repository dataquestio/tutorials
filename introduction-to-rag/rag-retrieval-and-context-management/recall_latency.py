import time
from gitquest import ask_gitquest

TEST_QUERIES = [
    ("how do I unstage a file I accidentally added?", "d5237eadab2f87ed"),
    ("how do I undo my last commit but keep my changes?", "ec4d8313b34c85a4"),
    ("how do I go back to a previous version of my file?", "90eb490de11828d8"),
    ("how do I see the commit history?", "eb1e19f70c96b73f"),
    ("how do I create a new branch?", "117d846e6e37c153"),
    ("how do I move commits from one branch to another?", "bc750e0e88a5bb43"),
    ("how do I rename a remote?", "70e8f045b665be41"),
]


def run_experiment(k, n_runs=3):
    total_times = []
    recalls = []

    for query, gold_id in TEST_QUERIES:
        found_in_any_run = False
        query_times = []

        for _ in range(n_runs):
            t0 = time.time()
            result = ask_gitquest(query, n_results=k)
            t1 = time.time()
            query_times.append(t1 - t0)

            if any(c["chunk_id"] == gold_id for c in result["retrieved_chunks"]):
                found_in_any_run = True

        total_times.append(sum(query_times) / n_runs)
        recalls.append(found_in_any_run)

    return {
        "k": k,
        "recall": sum(recalls) / len(recalls),
        "recalls": list(zip([q for q, _ in TEST_QUERIES], recalls)),
        "avg_total": sum(total_times) / len(total_times),
    }


for k in [5, 10, 20]:
    print(f"Running experiment for k={k}...")
    results = run_experiment(k)
    print(f"  Recall@5:  {results['recall']:.0%}")
    print(f"  Avg total: {results['avg_total']:.2f}s")
    print()
