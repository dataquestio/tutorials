"""Check a monitor's catalog against a rebuild that doesn't use the model.

It replays the days the checked folder's state.json lists as done into an
empty catalog, then compares the result with the folder's own catalog. If
they match, the folder's catalog is exactly what those days should produce.

Usage:
    python debug_catalog.py --data-dir data/usgs --workspace monitor
"""

import argparse
import shutil
from pathlib import Path

import tools
from run import prepare_workspace
from runner import load_state


REBUILD_DIR = Path("catalog_rebuild")


def completed_days(workspace):
    """The days the folder's state.json lists as done."""
    # TODO:
    # - Load the state from the folder's state/ subfolder
    # - Return its completed_days
    ...


def rebuild_catalog(data_dir, days):
    """Apply each day to an empty catalog in catalog_rebuild/ and return it."""
    # TODO:
    # - Clear REBUILD_DIR and link the feed into it
    # - Point the tools at REBUILD_DIR and apply each day
    # - Return the rebuilt catalog
    ...


def load_checked(workspace):
    """The catalog in the folder being checked."""
    # TODO:
    # - Point the feed tools at the folder
    # - Return its catalog
    ...


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, help="Folder with the days/ feed files")
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()

    days = completed_days(args.workspace)
    if days is None:
        print("completed_days returned None. Fill it in first.")
    elif not days:
        print(f"No completed days in {args.workspace} yet. Run the monitor first.")
    else:
        rebuilt = rebuild_catalog(args.data_dir, days)
        checked = load_checked(args.workspace)
        if rebuilt is None or checked is None:
            print("rebuild_catalog or load_checked returned None. Fill them in first.")
        else:
            print(f"Completed days in {args.workspace}: {days[0]} to {days[-1]} ({len(days)} days)")
            print(f"Rebuilt without the model: {len(rebuilt)} events")
            print(f"Catalog in {args.workspace}: {len(checked)} events")
            print(f"Identical: {rebuilt == checked}")
