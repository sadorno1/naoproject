"""Run `python setup_keys.py` from the repo to configure OpenAI without editing code."""
import argparse
import getpass
import os
from pathlib import Path
import re
import tempfile
import warnings

ENV_PATH = Path(__file__).resolve().parent / "experiment" / ".env"
KEY_LINE = re.compile(r"^\s*(?:export\s+)?OPENAI_API_KEY\s*=")


def save_key(path, key):
    """Replace only this setting, preserving unrelated values and comments."""
    key = key.strip()
    if not key or any(c.isspace() for c in key) or not all(c.isascii() and c.isalnum() or c in "_-" for c in key):
        raise ValueError("Use the API key only, without quotes, spaces or OPENAI_API_KEY=.")
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    new_lines = []
    replaced = False
    for line in lines:
        if KEY_LINE.match(line):
            if not replaced:
                new_lines.append("OPENAI_API_KEY=" + key)
                replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append("OPENAI_API_KEY=" + key)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".env.", suffix=".tmp", delete=False) as f:
            pending = Path(f.name)
            os.chmod(pending, 0o600)
            f.write("\n".join(new_lines) + "\n")
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Save your OpenAI API key locally using hidden input. No API calls are made.")
    parser.parse_args(argv)
    print("Configure OpenAI for NAO speech, transcription, dialogue and photo checks.")
    print("Your input is hidden. The key is saved locally in experiment/.env (not uploaded by Git).")
    print("Press Enter without a key to leave the current setup unchanged.")
    try:
        with warnings.catch_warnings():
            #Do not fall back to visible input when no real terminal is available.
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("OpenAI API key: ")
        if not key.strip():
            print("No changes made.")
            return 0
        save_key(ENV_PATH, key)
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled. No key was saved.")
        return 1
    except getpass.GetPassWarning:
        print("Hidden input is unavailable. Run python setup_keys.py in a normal terminal.")
        return 1
    except ValueError as e:
        print(str(e))
        return 1
    except OSError:
        print("Could not save experiment/.env. Check that this folder is writable and try again.")
        return 1
    print("Saved. The project loads this key automatically; restart any running session.")
    print("The key has not been checked with OpenAI. You can rerun this command to replace it.")
    if os.environ.get("OPENAI_API_KEY"):
        print("Your terminal also has OPENAI_API_KEY set; it takes priority over the saved file.")
        print("On Linux, run: unset OPENAI_API_KEY  (to use the saved file instead).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
