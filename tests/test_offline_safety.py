"""Offline regression suite for crucial safety logic; requires no Telegram account or MongoDB.

Run: python -m unittest tests.test_offline_safety -v
Tests extract the real async worker functions from the source AST so they can be
executed without installing the bot's third-party runtime dependencies.
"""

import ast
import asyncio
import inspect
import logging
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

BASE = Path(__file__).resolve().parents[1]


def extract_functions(path, names, env):
    tree = ast.parse((BASE / path).read_text(encoding="utf-8"))
    funcs = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name in names]
    # Production imports are already verified separately; avoid activating bot/__init__
    # in this dependency-free test by using an equivalent injected function.
    class ReplaceInternalNotionImport(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.module == "bot.utils.notion_settings":
                return None
            return node
    funcs = [ReplaceInternalNotionImport().visit(f) for f in funcs]
    assert {f.name for f in funcs} == set(names), (path, names)
    code = compile(ast.fix_missing_locations(ast.Module(body=funcs, type_ignores=[])), str(path), "exec")
    exec(code, env)
    return [env[n] for n in names]


class TestNoRollback(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_does_not_delete_any_telegram_copy_or_ledger(self):
        scope = {"__name__": "safety_rollback", "logger": logging.getLogger("safety_rollback")}
        [fn] = extract_functions('bot/backup/rollback.py', ['rollback_message_delivery'], scope)
        bot = MagicMock(delete_messages=AsyncMock(side_effect=AssertionError('delete')))
        app = MagicMock(delete_messages=AsyncMock(side_effect=AssertionError('delete')))
        await fn(bot, app, -100, 1)
        bot.delete_messages.assert_not_called()
        app.delete_messages.assert_not_called()


class FakeTaskDB:
    def __init__(self, task):
        self.task = task
        self.batch_tasks = self
        self.checkpoints = []

    async def read(self, task_id):
        return dict(self.task)

    async def set_control(self, task_id, control, **kw):
        self.task.update({"control": control, **kw})

    async def set_worker_state(self, task_id, **kw):
        self.task.update(kw)

    async def update_progress(self, task_id, current_message_id, count):
        self.task.update(current_message_id=current_message_id, processed_count=count)
        self.checkpoints.append(current_message_id)

    async def update_status(self, task_id, status, count=None):
        self.task['status'] = status
        if count is not None:
            self.task['processed_count'] = count

    async def update(self, task_id, fields):
        self.task.update(fields)

    async def resolve_message_failures(self, *args):
        return None

    async def clear_control(self, *a, **kw):
        self.task['control'] = None


class TestSafeCheckpoint(unittest.IsolatedAsyncioTestCase):
    def worker(self, db, process, state=None):
        env = {
            'db': db,
            'Client': MagicMock,
            'safe_status_message': lambda bot, uid, text: bot.send_message(uid, text),
            'notion_enabled_for_user': lambda user_id, enabled: enabled,
            'process_message_item': process,
            'ControlCommand': SimpleNamespace(CANCEL=SimpleNamespace(value='cancel'), STOP=SimpleNamespace(value='stop'), PAUSE=SimpleNamespace(value='pause')),
            'WorkerPhase': SimpleNamespace(PROCESSING=SimpleNamespace(value='processing'), DRAINING=SimpleNamespace(value='draining'), STOPPED=SimpleNamespace(value='stopped'), PAUSED=SimpleNamespace(value='paused'), IDLE=SimpleNamespace(value='idle')),
            'Config': SimpleNamespace(BATCH_SLEEP_TIME=0),
            'logger': logging.getLogger('offline'),
            'CancelledError': type('CancelledError', (Exception,), {}),
            'interruptible_sleep': AsyncMock(return_value=False),
        }
        async def check(task_id):
            task = await db.read(task_id)
            if task['status'] in ('paused','stopped','failed','completed'):
                return True, task['status']
            if task.get('control') in ('pause', 'cancel', 'stop'):
                return True, task['control']
            return False,None
        env['batch_should_halt']=check
        return extract_functions('bot/utils/batch/worker.py', ['run_batch_loop', 'complete_or_pause_task'], env)

    def initial(self, first=10, last=12):
        return dict(_id=77, status='running', control=None, current_message_id=first,
                    last_message_id=last, first_message_id=first, source_chat_id=-100,
                    processed_count=0, notion_enabled=False)

    async def test_retry_stops_at_failing_message_without_advancing_checkpoint(self):
        state=self.initial()
        db=FakeTaskDB(state)
        processed=[]
        async def process(*args,**kwargs):
            msg_id=args[3]
            processed.append(msg_id)
            return (None,False) if msg_id==11 else (True,False)
        run,_=self.worker(db,process)
        count=await run(MagicMock(),MagicMock(),state,77,1)
        self.assertEqual(processed,[10,11]);self.assertEqual(db.task['current_message_id'],11)
        self.assertEqual(db.task['retry_message_id'],11)
        self.assertEqual(db.task['status'],'paused');self.assertEqual(count,1)

    async def test_resume_retries_failed_message_not_earlier_success(self):
        state=self.initial()
        db=FakeTaskDB(state)
        processed=[]
        async def first(*a,**k):
            processed.append(a[3]);return (None,False) if a[3]==11 else (True,False)
        run,_=self.worker(db,first)
        await run(MagicMock(),MagicMock(),state,77,1)
        db.task['status']='running'
        resumed=dict(db.task)
        processed=[]
        async def second(*a,**k):
            processed.append(a[3]);return True,False
        run,complete=self.worker(db,second)
        await run(MagicMock(),MagicMock(),resumed,77,1)
        self.assertEqual(processed,[11,12]);self.assertEqual(db.task['current_message_id'],13)
        self.assertIsNone(db.task.get('retry_message_id'))
        await complete(MagicMock(send_message=AsyncMock()),77,1,3)
        self.assertEqual(db.task['status'],'completed')

    async def test_concurrent_cancel_is_not_reset_by_worker_state(self):
        state=self.initial()
        db=FakeTaskDB(state)
        processed=[]
        async def process(*a,**k):
            processed.append(a[3])
            db.task['control']='cancel'
            return True,False
        run,_=self.worker(db,process)
        await run(MagicMock(),MagicMock(),state,77,1)
        self.assertEqual(processed,[10])
        self.assertEqual(db.task['control'],'cancel')

    async def test_does_not_complete_when_last_id_not_processed(self):
        state=self.initial(first=10,last=12)
        db=FakeTaskDB(state)
        _,complete=self.worker(db,AsyncMock())
        await complete(MagicMock(send_message=AsyncMock()),77,1,0)
        self.assertEqual(db.task['status'],'paused')


class TestBootRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_restart_pauses_stale_task_without_auto_transfer(self):
        task=dict(_id=77,user_id=1,current_message_id=999)
        actions=[]
        class Tasks:
            async def filter_documents(self,query):
                return [task]
            async def update_status(self, task_id, status):
                actions.append(('status',status))
            async def clear_control(self, task_id, worker_phase=None):
                actions.append(('phase',worker_phase))
        env={
            'db':SimpleNamespace(batch_tasks=Tasks()),
            'Config':SimpleNamespace(BATCH_AUTO_RESUME_ON_START=False),
            'WorkerPhase':SimpleNamespace(PAUSED=SimpleNamespace(value='paused'),PROCESSING=SimpleNamespace(value='processing')),
            'logger':logging.getLogger('offline'),
            'Client':MagicMock,
        }
        [fn]=extract_functions('bot/utils/batch/resume.py',['resume_interrupted_batches'],env)
        resumed=await fn(MagicMock(send_message=AsyncMock()))
        self.assertEqual(resumed,0)
        self.assertIn(('status','paused'),actions)
        self.assertNotIn(('status','running'),actions)


class TestSafeArchive(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Load real archive logic independent of bot/__init__.py and Telegram.
        import runpy
        self.api=runpy.run_path(str(BASE/'bot/utils/archive_handler.py'))

    def archive(self,members):
        target=Path(self.tmp.name)/'input.zip'
        with zipfile.ZipFile(target,'w') as z:
            for k,v in members.items(): z.writestr(k,v)
        return str(target)

    def test_extract_small_archive(self):
        src=self.archive({'a.stl':b'abc','folder/b.3mf':b'1234'})
        dest=Path(self.tmp.name)/'out'
        files=self.api['extract_archive'](src,str(dest),max_files=2,max_total_size=10)
        self.assertEqual(len(files),2)
        self.assertEqual((dest/'a.stl').read_bytes(),b'abc')

    def test_reject_traversal(self):
        src=self.archive({'../escape.stl':b'abc'})
        dest=Path(self.tmp.name)/'out'
        with self.assertRaises(self.api['ArchiveHandlerError']):
            self.api['extract_archive'](src,str(dest))
        self.assertFalse((Path(self.tmp.name)/'escape.stl').exists())

    def test_reject_too_many_members_before_extraction(self):
        src=self.archive({'1.stl':b'a','2.stl':b'b'})
        dest=Path(self.tmp.name)/'out'
        with self.assertRaises(self.api['ArchiveHandlerError']):
            self.api['extract_archive'](src,str(dest),max_files=1)
        self.assertFalse((dest/'1.stl').exists())

    def test_reject_size_over_limit_before_extraction(self):
        src=self.archive({'a.stl':b'a'*1024})
        dest=Path(self.tmp.name)/'out'
        with self.assertRaises(self.api['ArchiveHandlerError']):
            self.api['extract_archive'](src,str(dest),max_total_size=100)
        self.assertFalse((dest/'a.stl').exists())

    def test_reject_zip_symlink(self):
        src=Path(self.tmp.name)/'input.zip'; info=zipfile.ZipInfo('pointer')
        info.create_system=3; info.external_attr=(0o120777<<16)
        with zipfile.ZipFile(src,'w') as z:z.writestr(info,'/etc/passwd')
        with self.assertRaises(self.api['ArchiveHandlerError']):
            self.api['extract_archive'](str(src),str(Path(self.tmp.name)/'out'))

if __name__ == '__main__': unittest.main()
