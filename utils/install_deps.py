"""Utility for installing dependencies from a requirements file."""
import argparse
import subprocess
import sys
from pathlib import Path


def install(requirements: str) -> None:
    """Install dependencies listed in the given requirements file.

    The function avoids invoking a shell to prevent command injection and
    validates that the provided requirements path points to a file.
    """
    req_path = Path(requirements).expanduser().resolve()
    if not req_path.is_file():
        raise FileNotFoundError(f"Requirements file not found: {req_path}")

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req_path)],
        check=True,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Install dependencies safely")
    parser.add_argument(
        "requirements",
        help="Path to requirements file to install",
    )
    args = parser.parse_args(argv)
    install(args.requirements)


if __name__ == "__main__":
    main()
