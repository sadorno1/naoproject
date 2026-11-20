#pre-generates the cached audio for the fixed lines (greeting, 3 "take a look" lines, goodbye)
#run it after editing prompts/fixed_lines.json, so the first session does not wait for TTS.
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
    texts = [lines["greeting"], *lines["look"], lines["goodbye"]]
    #Cache reviewed step instructions too; drafts must not prevent caching the basic phrases.
    from build_workflow import BuildWorkflow
    try:
        workflow = BuildWorkflow()
    except (ValueError, OSError) as e:
        print(f"Step instructions not ready for caching: {e}")
    else:
        for i in range(len(workflow.steps)):
            workflow.index = i
            texts.append(workflow.announcement())
    texts.extend([
        "Yes, that's correct! Okay, next step.",
        "Yes, that's correct! We're all done.",
        "No, not quite yet. Let's try this step again.",
        "I can't see clearly enough to check. Move your hands away and press my left foot bumper to try again.",
        "I couldn't check that photo. Please clear the view and press my left foot bumper to try again.",
    ])
    for text in texts:
        existed = os.path.exists(tts.cache_path(text))
        path = tts.ensure_cached(text)
        print(f"{'cached ' if existed else 'created'} {os.path.basename(path)}  {text!r}")
    print(f"\nModel {tts.model}, voice {tts.voice}. Cache folder: {config.AUDIO_CACHE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
