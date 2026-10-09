import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('notify_platforms', ROOT / 'scripts/notify.py')
n = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n)


class PlatformTests(unittest.TestCase):
    def test_assets_are_distinct_short_pcm_wav(self):
        contents = []
        for kind in n.SOUNDS:
            file = ROOT / 'assets' / (kind + '.wav')
            contents.append(file.read_bytes())
            with wave.open(str(file)) as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), 44100)
                self.assertLess(wav.getnframes() / wav.getframerate(), 1.5)
                self.assertGreater(wav.getnframes(), 1000)
        self.assertEqual(len(set(contents)), 3)

    def test_selected_c_assets_are_reproducible(self):
        spec = importlib.util.spec_from_file_location('sound_generator', ROOT / 'scripts/generate_sounds.py')
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        for kind in n.SOUNDS:
            with wave.open(str(ROOT / 'assets' / (kind + '.wav'))) as wav:
                self.assertEqual(generator.render(kind), wav.readframes(wav.getnframes()))

    def test_windows_uses_bounded_synchronous_player(self):
        with patch.object(n.sys, 'platform', 'win32'), patch.object(n.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertTrue(n.play('input'))
            args = run.call_args.args[0]
            self.assertEqual(args[:2], [sys.executable, '-c'])
            self.assertIn('SND_FILENAME', args[2])
            self.assertIn('SND_NODEFAULT', args[2])
            self.assertNotIn('SND_ASYNC', args[2])
            self.assertEqual(args[-1], str(n.ASSETS / 'input.wav'))
            self.assertLessEqual(run.call_args.kwargs['timeout'], 5)
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_linux_backend_order(self):
        with patch.object(n.sys, 'platform', 'linux'), patch.object(n.shutil, 'which', side_effect=lambda x: '/usr/bin/' + x):
            self.assertEqual([c[0] for c in n.player_commands(Path('a b.wav'))],
                             ['/usr/bin/pw-play', '/usr/bin/paplay', '/usr/bin/aplay'])

    def test_linux_falls_back_on_error_and_timeout(self):
        outcomes = [Mock(returncode=1), subprocess.TimeoutExpired('paplay', 2), Mock(returncode=0)]
        with patch.object(n.sys, 'platform', 'linux'), patch.object(n.shutil, 'which', side_effect=lambda x: '/usr/bin/' + x), patch.object(n.subprocess, 'run', side_effect=outcomes) as run:
            self.assertTrue(n.play('approval'))
            self.assertEqual(run.call_count, 3)
            for call in run.call_args_list:
                self.assertNotIn('shell', call.kwargs)
                self.assertLessEqual(call.kwargs['timeout'], 5)

    def test_linux_fallback_shares_deadline(self):
        with patch.object(n.sys, 'platform', 'linux'), patch.object(n.shutil, 'which', side_effect=lambda x: x), patch.object(n.time, 'monotonic', side_effect=[10, 10, 12, 14]), patch.object(n.subprocess, 'run', return_value=Mock(returncode=1)) as run, patch.object(n.sys, 'stderr', new=io.StringIO()):
            self.assertFalse(n.play('complete'))
            self.assertEqual([c.kwargs['timeout'] for c in run.call_args_list], [2, 2, 1])

    def test_linux_missing_backends_is_nonfatal(self):
        with patch.object(n.sys, 'platform', 'linux'), patch.object(n.shutil, 'which', return_value=None), patch.object(n.subprocess, 'run') as run, patch.object(n.sys, 'stderr', new=io.StringIO()):
            self.assertFalse(n.play('input'))
            run.assert_not_called()

    def test_backend_os_error_is_nonfatal(self):
        with patch.object(n.sys, 'platform', 'darwin'), patch.object(n.subprocess, 'run', side_effect=OSError('device unavailable')), patch.object(n.sys, 'stderr', new=io.StringIO()):
            self.assertFalse(n.play('input'))

    def test_unknown_platform(self):
        with patch.object(n.sys, 'platform', 'unknown'), patch.object(n.subprocess, 'run') as run, patch.object(n.sys, 'stderr', new=io.StringIO()):
            self.assertFalse(n.play('complete'))
            run.assert_not_called()

    def test_missing_asset_and_invalid_kind(self):
        with patch.object(n.Path, 'is_file', return_value=False), patch.object(n.subprocess, 'run') as run, patch.object(n.sys, 'stderr', new=io.StringIO()):
            self.assertFalse(n.play('input'))
            self.assertFalse(n.play('../input'))
            run.assert_not_called()

    def test_data_directory_overrides(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'PLUGIN_DATA': directory, 'CLAUDE_PLUGIN_DATA': 'ignored'}, clear=True):
            self.assertEqual(n.data_directory(), Path(directory))
        with patch.dict(os.environ, {'CLAUDE_PLUGIN_DATA': 'compatibility-data'}, clear=True):
            self.assertEqual(n.data_directory(), Path('compatibility-data'))

    def test_platform_cache_defaults(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(n.Path, 'home', return_value=Path('/home/demo')):
            for platform, suffix in [('darwin','Library/Caches/codex-sounds'), ('linux','.cache/codex-sounds'), ('win32','AppData/Local/codex-sounds')]:
                with patch.object(n.sys, 'platform', platform):
                    self.assertEqual(n.data_directory(), Path('/home/demo') / suffix)

    def test_platform_cache_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            for platform, variable in [('linux', 'XDG_CACHE_HOME'), ('win32', 'LOCALAPPDATA')]:
                with patch.object(n.sys, 'platform', platform), patch.dict(os.environ, {variable: directory}, clear=True):
                    self.assertEqual(n.data_directory(), Path(directory) / 'codex-sounds')
        with patch.object(n.sys, 'platform', 'linux'), patch.dict(os.environ, {'XDG_CACHE_HOME': 'relative'}, clear=True), patch.object(n.Path, 'home', return_value=Path('/home/demo')):
            self.assertEqual(n.data_directory(), Path('/home/demo/.cache/codex-sounds'))

    def test_audio_failure_does_not_change_hook_contract(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'PLUGIN_DATA': directory, 'CODEX_SOUNDS_MUTE': '0'}), patch.object(n.sys, 'argv', ['notify.py']), patch.object(n.sys, 'stdin', io.StringIO('{"hook_event_name":"Stop","turn_id":"t"}')), patch.object(n.sys, 'stdout', new=io.StringIO()) as output, patch.object(n, 'play', side_effect=OSError('audio error')), patch.object(n.sys, 'stderr', new=io.StringIO()):
            self.assertEqual(n.main(), 0)
            self.assertEqual(json.loads(output.getvalue()), {})

    def test_preview_reports_failure(self):
        with patch.object(n.sys, 'argv', ['notify.py', '--preview', 'input']), patch.object(n, 'play', return_value=False):
            self.assertEqual(n.main(), 1)

    def test_launchers_with_unicode_and_spaces(self):
        # Run the actual configured hook entry point on this host, never audio.
        hooks = json.loads((ROOT / 'hooks/hooks.json').read_text())['hooks']
        handler = hooks['Stop'][0]['hooks'][0]
        self.assertIn('commandWindows', handler)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / '插件 with spaces'
            shutil.copytree(ROOT / 'scripts', root / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
            env = dict(os.environ, PLUGIN_ROOT=str(root), CODEX_SOUNDS_MUTE='1')
            payload = '{"hook_event_name":"Stop","last_assistant_message":"完成"}'
            if os.name == 'nt':
                result = subprocess.run(handler['commandWindows'], shell=True, input=payload.encode('utf8'), capture_output=True, env=env, timeout=15)
            else:
                result = subprocess.run(['sh', '-c', handler['command']], input=payload.encode('utf8'), capture_output=True, env=env, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})
            # Also validate the Windows -c bootstrap independently of shell syntax.
            parts = shlex.split(handler['commandWindows'])
            parts[0] = sys.executable
            result = subprocess.run(parts, input=payload.encode('utf8'), capture_output=True, env=env, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})


if __name__ == '__main__':
    unittest.main()
