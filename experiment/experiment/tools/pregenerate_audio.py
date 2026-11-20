#pre-generates the cached audio for the fixed lines (greeting, 3 "take a look" lines, goodbye)
#run it after editing fixed_lines.json, so the first session does not wait for TTS.
#run_session.py also generates any missing file at startup, before the participant is greeted
#usage: python tools/pregenerate_audio.py
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config
from run_session import load_fixed_lines


def main():
    from dotenv import load_dotenv
    from openai import OpenAI
    from speech import TTS
    load_dotenv(config.DOTENV_PATH)
    tts = TTS(OpenAI())
    lines = load_fixed_lines()
    texts = [lines["greeting"], *lines["look"], lines["goodbye"], lines["early_goodbye"]]
    #Cache reviewed step instructions too; drafts must not prevent caching the basic phrases.
    from build_workflow import ACTIVITIES, BuildWorkflow
    for activity in ACTIVITIES:
        try:
            workflow = BuildWorkflow(only=activity)
        except (ValueError, OSError) as e:
            print(f"Instructions not ready for caching ({activity}): {e}")
        else:
            for i in range(len(workflow.steps)):
                workflow.index = i
                texts.append(workflow.announcement())
    texts.append("We'll practice checking next. First, hold the bumper on my foot that says talk while you speak, then let go.")
    texts.extend([
        "That's it, nice work!",
        "Nice work, you finished it! Ready to try the next build?",
        "You did it! Thanks for building with me. That was fun!",
        "I can't see clearly enough to check. Move your hands away and press the bumper on my foot that says check to try again.",
        "I couldn't check that photo. Please clear the view and press the bumper on my foot that says check to try again.",
    ])
    for text in texts:
        existed = os.path.exists(tts.cache_path(text))
        path = tts.ensure_cached(text)
        print(f"{'cached ' if existed else 'created'} {os.path.basename(path)}  {text!r}")
    print(f"\nModel {tts.model}, voice {tts.voice}. Cache folder: {config.AUDIO_CACHE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
