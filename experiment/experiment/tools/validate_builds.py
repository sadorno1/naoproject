"""Check authored steps, photo paths and shared phrases without a robot or API key."""
import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_workflow import ACTIVITIES, BUILDS_DIR, BuildWorkflow
from run_session import load_fixed_lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activity", choices=ACTIVITIES)
    parser.add_argument("--builds-dir", default=BUILDS_DIR)
    args = parser.parse_args(argv)
    try:
        load_fixed_lines()
        workflow = BuildWorkflow(args.builds_dir, only=args.activity)
    except (OSError, ValueError) as e:
        print(f"Not ready: {e}")
        return 1
    counts = Counter(s["activity"] for s in workflow.steps)
    for activity, count in counts.items():
        photos = sum(s["reference_photo"] is not None for s in workflow.steps if s["activity"] == activity)
        print(f"{activity}: {count} steps, {photos} readable reference photos")
    print("Shared phrases and authored steps passed offline validation. No robot or API calls were made.")
    print("Next: cache audio and rehearse on NAO; photo accuracy still needs live testing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
