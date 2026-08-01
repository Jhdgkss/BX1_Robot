import struct
import tempfile
from types import SimpleNamespace
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from audio_io import SpeakerController, _bx1_play_file, _bx1_player_command
from main import BX1RobotBodyService
import main as main_module


class SpeakerControlTests(unittest.TestCase):
    def test_loopback_passes_explicit_volume_and_does_not_use_config_fallback_for_playback(self):
        source = (Path(__file__).resolve().parents[1] / 'python' / 'main.py').read_text(encoding='utf-8')
        self.assertIn('self.web_test_speech(phrase, volume_percent=volume', source)
        self.assertNotIn('self.cfg["tts_volume"] = volume', source)

    def test_faster_whisper_rejection_is_not_unavailable(self):
        source = (Path(__file__).resolve().parents[1] / 'python' / 'main.py').read_text(encoding='utf-8')
        self.assertIn('stt_backend.startswith("brain_faster_whisper")', source)
    def test_explicit_device_and_volume_command(self):
        cmd = _bx1_player_command('/usr/bin/aplay', '/tmp/test.wav', 50, wav=True, playback_device='plughw:CARD=Device,DEV=0')
        self.assertEqual(cmd, ['/usr/bin/aplay', '-D', 'plughw:CARD=Device,DEV=0', '/tmp/test.wav'])

    @patch('audio_io.subprocess.run')
    @patch('audio_io.shutil.which', return_value='/usr/bin/amixer')
    def test_mixer_apply_and_readback(self, which, run):
        run.side_effect = [type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})(), type('R', (), {'returncode': 0, 'stdout': '[40%]', 'stderr': ''})()]
        state = SpeakerController().apply(40)
        self.assertTrue(state['apply_ok'])
        self.assertEqual(state['effective_volume_percent'], 40)

    @patch('audio_io.subprocess.run')
    def test_output_pcm_signal_is_reported(self, run):
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            name = f.name
        with wave.open(name, 'wb') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000); wf.writeframes(struct.pack('<hhhh', 0, 1000, -2000, 0))
        run.return_value = type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
        report = _bx1_play_file('/usr/bin/aplay', name, 40, wav=True, playback_device='plughw:CARD=Device,DEV=0')
        self.assertIsNotNone(report['output_rms_dbfs']); self.assertTrue(report['output_non_silent'])

    @patch('audio_io.subprocess.run')
    def test_six_second_tts_duration_is_available_for_loopback_timeout(self, run):
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            name = f.name
        with wave.open(name, 'wb') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
            wf.writeframes(struct.pack('<h', 1200) * (16000 * 6))
        run.return_value = type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
        report = _bx1_play_file('/usr/bin/aplay', name, 40, wav=True, playback_device='plughw:CARD=Device,DEV=0')
        self.assertAlmostEqual(report['generated_audio_duration_s'], 6.0, places=2)
        self.assertGreaterEqual(report['generated_audio_duration_s'] + 3.0, 9.0)

    def test_loopback_completion_and_timeout_contracts_are_present(self):
        source = (Path(__file__).resolve().parents[1] / 'python' / 'main.py').read_text(encoding='utf-8')
        self.assertIn('playback_ready.wait(timeout=120.0)', source)
        self.assertIn('playback_timeout_s = max(3.0, generated_duration + 3.0)', source)
        self.assertIn('playback_ready.set()', source)
        self.assertIn('playback_done.set()', source)
        self.assertIn('os.replace(part, target)', source)

    def test_real_web_test_speech_path_resolves_volume_helper(self):
        service = BX1RobotBodyService.__new__(BX1RobotBodyService)
        service.cfg = {'tts_volume': 80, 'brain_tts_base_url': ''}

        class FakeTTS:
            def __init__(self):
                self.cfg = SimpleNamespace(tts_volume=80, tts_playback_device='default')
                self.updated = []
            def update_config(self, cfg):
                self.cfg = cfg; self.updated.append(cfg)
            def test_speech_blocking(self, text, **kwargs):
                return {'ok': True, 'message': 'stub playback', 'text': text}

        service.tts = FakeTTS()
        service.build_audio_config = lambda: SimpleNamespace(tts_volume=80, tts_playback_device='default')
        service.resolve_brain_tts_base_url = lambda **kwargs: ''
        service.get_audio_settings = lambda: {}
        service.web_log = lambda *args, **kwargs: None
        result = service.web_test_speech('runtime helper test', volume_percent=37)
        self.assertTrue(result['ok'])
        self.assertEqual(service.tts.cfg.tts_volume, 37)

    def test_loopback_playback_failure_stops_capture_promptly_and_keeps_wav(self):
        service = BX1RobotBodyService.__new__(BX1RobotBodyService)
        service.cfg = {'tts_volume': 80, 'mic_device': 'default', 'sample_rate': 16000, 'mic_channels': 1, 'tts_playback_device': 'default'}
        service.loopback_cancel = threading.Event()
        service.loopback_capture_stop = threading.Event()
        service.manual_audio_capture_requested = threading.Event()
        service.audio_capture_lock = threading.Lock()
        service.loopback_lock = threading.Lock()
        service.loopback_session = {'capture_id': '', 'running': True, 'worker': None}
        service.loopback_state = {}
        service.loopback_wav = ''
        service.mic_monitor = SimpleNamespace(is_running=lambda: False)
        service.tts = SimpleNamespace(update_config=lambda cfg: None)
        service.build_audio_config = lambda: SimpleNamespace()
        service.web_stop_speaking = lambda: {'ok': True}
        service.web_test_speech = lambda *args, **kwargs: {'ok': False, 'report': {'ok': False, 'message': 'playback start failed'}}

        def fake_capture(filename, **kwargs):
            while not kwargs['stop_event'].is_set():
                time.sleep(0.01)
            with wave.open(str(filename), 'wb') as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000); wf.writeframes(struct.pack('<h', 900) * 1600)
            return {'ok': True, 'actual_duration_s': 0.1, 'analysis': {'peak_dbfs': -30.0}}

        started = time.perf_counter()
        with patch.object(main_module, 'record_microphone_sample', side_effect=fake_capture):
            result = service._run_loopback_test({'expected_phrase': 'fail fast', 'speaker_volume': 40, '_capture_id': 'test-fail-fast'})
        elapsed = time.perf_counter() - started
        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], 'playback_start_failed')
        self.assertLess(elapsed, 5.0)
        self.assertTrue(result['filename'])
        self.assertTrue(Path(result['filename']).is_file())
        Path(result['filename']).unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
