#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--defaults", required=True)
    args = ap.parse_args()
    path = Path(args.config)
    defaults_path = Path(args.defaults)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))

    # User-selected hardware, endpoints, wake words and voice identity remain intact.
    for key, value in defaults.items():
        cfg.setdefault(key, value)

    forced = {
        "app_version": "10.33",
        "version": "10.33",
        "stt_pre_roll_ms": 850,
        "stt_end_silence_ms": 1400,
        "stt_post_roll_ms": 320,
        "stt_start_trigger_ms": 120,
        "stt_adaptive_margin_db": 7.0,
        "stt_min_confidence": 0.40,
        "stt_repetition_guard_enabled": True,
        "stt_max_consecutive_word_repeats": 3,
        "stt_max_repeated_phrase_count": 2,
        "stt_min_unique_word_ratio": 0.30,
        "stt_max_words_per_second": 7.0,
        "stt_max_transcript_words": 90,
        "stt_reject_prompt_leakage": True,
        "wake_fuzzy_matching_enabled": True,
        "wake_fuzzy_threshold": 0.78,
        "wake_match_first_tokens": 4,
        "wake_command_window_s": 15.0,
        "conversation_followup_window_s": 90.0,
        "wake_voice_ack_enabled": True,
        "wake_ack_phrases": ["Yes John?", "I'm listening.", "Go ahead."],
        "thinking_feedback_enabled": True,
        "thinking_feedback_delay_s": 0.35,
        "thinking_cues_enabled": True,
        "thinking_cue_speak": True,
        "thinking_cue_delay_s": 1.8,
        "thinking_cue_repeat_s": 12.0,
        "thinking_cue_max_per_reply": 1,
        "brain_controls_thinking_cues": False,
        "brain_request_watchdog_s": 50.0,
        "stt_post_tts_guard_s": 1.0,
        "wake_after_reply_guard_s": 0.65,
    }
    cfg.update(forced)

    aliases = cfg.get("wake_word_aliases")
    if not isinstance(aliases, dict):
        aliases = dict(defaults.get("wake_word_aliases") or {})
    robot_aliases = aliases.get("robot", [])
    if isinstance(robot_aliases, str):
        robot_aliases = [x.strip() for x in robot_aliases.replace(",", "\n").splitlines() if x.strip()]
    aliases["robot"] = [x for x in robot_aliases if str(x).lower().strip() != "rowboat"]
    cfg["wake_word_aliases"] = aliases

    # Deliberately preserve wake_words exactly. Hello, Hey and Robot remain valid.
    path.write_text(json.dumps(cfg, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Migrated {path} to BX1 body {cfg.get('app_version')}")


if __name__ == "__main__":
    main()
