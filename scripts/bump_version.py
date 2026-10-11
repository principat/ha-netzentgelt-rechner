"""Update the version field in manifest.json. Used by semantic-release."""

import json
import sys
from pathlib import Path

MANIFEST_PATH = Path("custom_components/netzentgelt_rechner/manifest.json")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: bump_version.py <new-version>", file=sys.stderr)
        sys.exit(1)

    new_version = sys.argv[1]
    data = json.loads(MANIFEST_PATH.read_text())
    data["version"] = new_version
    MANIFEST_PATH.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Updated {MANIFEST_PATH} to version {new_version}")


if __name__ == "__main__":
    main()
