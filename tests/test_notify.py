import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('notify', ROOT / 'scripts/notify.py')
n = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n)

class SoundTests(unittest.TestCase):
    def event(self, name='Stop', **kwargs):
        return dict(hook_event_name=name, session_id='s1', turn_id='t1', **kwargs)

    def test_classification(self):
        for event, expected in [('Stop','complete'),('PermissionRequest','approval'),('PostToolUse',None),('Interrupt',None),('SubagentStop',None)]:
            self.assertEqual(n.classify(self.event(event)), expected)

    def test_questions(self):
        for tool in ['request_user_input','request_user_input_async','functions.request_user_input_async','mcp__server__AskUserQuestion']:
            self.assertEqual(n.classify(self.event('PreToolUse',tool_name=tool)), 'input')
        self.assertIsNone(n.classify(self.event('PreToolUse',tool_name='not_request_user_input_extra')))

    def test_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); e=self.event()
            self.assertTrue(n.claim(e,'complete',p,100))
            self.assertFalse(n.claim(e,'complete',p,101))
            self.assertTrue(n.claim(dict(e,turn_id='t2'),'complete',p,102))
            self.assertTrue(n.claim(dict(e,session_id='s2'),'complete',p,103))

    def test_distinct_questions(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); e=self.event('PreToolUse',tool_use_id='q1')
            self.assertTrue(n.claim(e,'input',p,100))
            self.assertFalse(n.claim(e,'input',p,101))
            self.assertTrue(n.claim(dict(e,tool_use_id='q2'),'input',p,101))

    def test_approval_without_call_id_repeats_after_cooldown(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); e=self.event('PermissionRequest',tool_input={'command':'ls'})
            self.assertTrue(n.claim(e,'approval',p,100))
            self.assertFalse(n.claim(e,'approval',p,101))
            self.assertTrue(n.claim(e,'approval',p,104))

    def test_async_question_suppresses_immediate_stop(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            n.claim(self.event('PreToolUse',tool_use_id='q'),'input',p,100)
            self.assertFalse(n.claim(self.event(),'complete',p,101))
            self.assertTrue(n.claim(self.event(),'complete',p,104))

    def test_missing_turn_does_not_mute_forever(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); e={'session_id':'s'}
            self.assertTrue(n.claim(e,'complete',p,100))
            self.assertTrue(n.claim(e,'complete',p,104))

    def test_concurrent_callbacks(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _: n.claim(self.event(),'complete',p,100),range(8)))
            self.assertEqual(sum(results),1)

    def test_no_prompt_text_in_state(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            n.claim(self.event('PreToolUse',tool_input={'secret':'sensitive-prompt-123'}),'input',p,100)
            self.assertNotIn(b'sensitive-prompt-123',(p/'events.sqlite3').read_bytes())

    def test_hook_output_contract(self):
        for value in ['{', '[]', json.dumps(self.event()), json.dumps(self.event('PermissionRequest'))]:
            r=subprocess.run([sys.executable,str(ROOT/'scripts/notify.py')],input=value,text=True,capture_output=True,env=dict(os.environ,CODEX_SOUNDS_MUTE='1'))
            self.assertEqual(r.returncode,0)
            self.assertEqual(json.loads(r.stdout),{})

    def test_play_no_shell(self):
        with patch.object(n.sys,'platform','darwin'), patch.object(n.Path,'is_file',return_value=True), patch.object(n.subprocess,'run') as run:
            run.return_value.returncode=0
            self.assertTrue(n.play('input'))
            self.assertEqual(run.call_args.args[0][0],'/usr/bin/afplay')
            self.assertNotIn('shell',run.call_args.kwargs)

    def test_audio_timeout_is_nonfatal(self):
        with patch.object(n.sys,'platform','darwin'), patch.object(n.Path,'is_file',return_value=True), patch.object(n.subprocess,'run',side_effect=subprocess.TimeoutExpired('afplay',5)):
            self.assertFalse(n.play('complete'))

    def test_hooks_match_classifier(self):
        import re
        h=json.loads((ROOT/'hooks/hooks.json').read_text())['hooks']
        self.assertEqual(set(h),{'Stop','PreToolUse','PermissionRequest'})
        self.assertTrue(re.search(h['PreToolUse'][0]['matcher'],'functions.request_user_input_async'))

if __name__ == '__main__': unittest.main()
