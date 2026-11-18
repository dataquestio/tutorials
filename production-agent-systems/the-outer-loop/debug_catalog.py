"""Check a monitor's catalog against a rebuild that doesn't use the model.

The imports, the command-line options, and the printed summary are provided.
Below the "YOUR CHECK" divider, each function already has its signature in
place and you fill in the body:
  - completed_days, to read which days the checked folder has finished
  - rebuild_catalog, to replay those days into an empty catalog
  - load_checked, to load the checked folder's catalog

Usage (once you've filled it in):
    python debug_catalog.py --data-dir data/usgs --workspace monitor
"""

import argparse
import shutil
from pathlib import Path

import tools
from run import prepare_workspace
from runner import load_state


REBUILD_DIR = Path("catalog_rebuild")


# ===========================================================================
# YOUR CHECK
# ===========================================================================


def completed_days(workspace):
    """The days the folder's state.json lists as done."""
    # Fill in the body. Return the completed_days list from the state in the
    # folder's state/ subfolder.
    ...


def rebuild_catalog(data_dir, days):
    """Apply each day to an empty catalog in catalog_rebuild/ and return it."""
    # shutil.rmtree deletes a folder and everything in it. ignore_errors=True
    # means it's fine if the folder isn't there yet, so every rebuild starts
    # from an empty catalog.
    shutil.rmtree(REBUILD_DIR, ignore_errors=True)
    prepare_workspace(REBUILD_DIR, Path(data_dir))
    # Fill in the rest. Point the feed tools at REBUILD_DIR, apply each of the
    # days, and return the rebuilt catalog.
    ...


def load_checked(workspace):
    """The catalog in the folder being checked."""
    # Fill in the body. Point the feed tools at the folder and return its
    # catalog.
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
