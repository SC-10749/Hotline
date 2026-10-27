import json
import sys
import tempfile
import threading
import unittest
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage]
    requests: list = Field(default_factory=list)
    tools_seen: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return 'offline-scripted-model'

    def bind_tools(self, tools: Sequence, **kwargs):
        self.tools_seen.extend(tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.requests.append(list(messages))
        response = self.responses[len(self.requests) - 1]
        return ChatResult(generations=[ChatGeneration(message=response)])


def call_file(uri, identity='call-1', **arguments):
    return AIMessage(content='', tool_calls=[{
        'name': 'read_file', 'args': {'resource_uri': uri, **arguments}, 'id': identity,
    }])


class AgentToolTests(unittest.TestCase):
    def run_model(self, model, reader, stopped=lambda: False):
        from python_backend.modules.execution.langchain_agent import run_agent
        from python_backend.modules.execution.tools import build_read_file_tool
        return list(run_agent(model, '技能目录 demo skill://demo/SKILL.md', '当前问题',
                              [build_read_file_tool(reader)], stopped))

    def test_progressive_tool_loop_without_history_or_tool_description_catalog(self):
        entry = 'skill://demo/SKILL.md'
        reference = 'skill://demo/references/guide.md'
        model = ScriptedModel(responses=[call_file(entry), call_file(reference, 'call-2'), AIMessage(content='最终答案')])
        reader = Mock(side_effect=[{'text': 'BODY_SENTINEL'}, {'text': 'REFERENCE_SENTINEL'}])
        events = self.run_model(model, reader)
        self.assertEqual([event.type for event in events], ['text', 'done'])
        self.assertEqual(events[0].content, '最终答案')
        self.assertEqual(len(model.requests), 3)
        self.assertEqual([message.type for message in model.requests[0]], ['system', 'human'])
        self.assertNotIn('BODY_SENTINEL', repr(model.requests[0]))
        self.assertIn('BODY_SENTINEL', repr(model.requests[1]))
        self.assertNotIn('REFERENCE_SENTINEL', repr(model.requests[1]))
        self.assertIn('REFERENCE_SENTINEL', repr(model.requests[2]))
        self.assertNotIn('skill://demo', model.tools_seen[0].description)
        self.assertEqual(reader.call_count, 2)

    def test_bad_arguments_and_unknown_tools_never_execute_reader(self):
        model = ScriptedModel(responses=[
            AIMessage(content='', tool_calls=[{'name': 'demo', 'args': {}, 'id': 'bad-tool'}]),
            AIMessage(content='', tool_calls=[{'name': 'read_file', 'args': {'offset': 'invalid'}, 'id': 'bad-args'}]),
            AIMessage(content='无法读取'),
        ])
        reader = Mock()
        events = self.run_model(model, reader)
        reader.assert_not_called()
        self.assertEqual(events[-1].type, 'done')
        self.assertTrue(any(isinstance(message, ToolMessage) and message.status == 'error'
                            for message in model.requests[-1]))

    def test_model_calls_are_bounded(self):
        model = ScriptedModel(responses=[call_file('skill://demo/SKILL.md', f'call-{number}') for number in range(10)])
        events = self.run_model(model, Mock(return_value={'text': 'x'}))
        self.assertEqual(len(model.requests), 8)
        self.assertEqual(events[-1].type, 'error')
        self.assertNotIn('done', [event.type for event in events])

    def test_parallel_tool_requests_are_bounded(self):
        model = ScriptedModel(responses=[AIMessage(content='', tool_calls=[
            {'name': 'read_file', 'args': {'resource_uri': 'skill://demo/SKILL.md'}, 'id': f'call-{number}'}
            for number in range(17)
        ])])
        reader = Mock(return_value={'text': 'x'})
        events = self.run_model(model, reader)
        self.assertLessEqual(reader.call_count, 16)
        self.assertEqual(events[-1].type, 'error')

    def test_stop_before_and_after_model_prevents_tools_and_success(self):
        stopped = threading.Event()
        model = ScriptedModel(responses=[call_file('skill://demo/SKILL.md')])
        reader = Mock()
        stopped.set()
        events = self.run_model(model, reader, stopped.is_set)
        self.assertEqual(len(model.requests), 0)
        self.assertEqual(events[-1].type, 'error')
        stopped.clear()
        original = ScriptedModel._generate

        def stop_after_model(instance, *args, **kwargs):
            result = original(instance, *args, **kwargs)
            stopped.set()
            return result

        with patch.object(ScriptedModel, '_generate', stop_after_model):
            events = self.run_model(model, reader, stopped.is_set)
        reader.assert_not_called()
        self.assertEqual(events[-1].type, 'error')

    def test_duplicate_call_ids_are_protocol_error(self):
        model = ScriptedModel(responses=[call_file('skill://demo/SKILL.md'), call_file('skill://demo/SKILL.md')])
        reader = Mock(return_value={'text': 'x'})
        events = self.run_model(model, reader)
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(events[-1].type, 'error')

    def test_tool_output_budget_and_errors_are_sanitized(self):
        model = ScriptedModel(responses=[call_file('skill://demo/SKILL.md', f'call-{number}') for number in range(8)])
        events = self.run_model(model, Mock(return_value={'text': 'x' * 12000}))
        self.assertEqual(events[-1].type, 'error')
        sensitive_error = 'FAKE_PRIVATE_SENTINEL'
        events = self.run_model(ScriptedModel(responses=[call_file('skill://demo/SKILL.md')]),
                                Mock(side_effect=RuntimeError(sensitive_error)))
        self.assertEqual(events[-1].type, 'error')
        self.assertNotIn(sensitive_error, repr(events))

    def test_model_factory_maps_configuration_without_network(self):
        from python_backend.llm import build_chat_model
        settings = SimpleNamespace(model_api_key='placeholder-test-key', model_name='test-model',
                                   model_base_url='http://127.0.0.1:9/v1')
        model = build_chat_model(settings)
        self.assertEqual(model.model_name, 'test-model')
        self.assertEqual(model.openai_api_base, settings.model_base_url)
        self.assertEqual(model.max_retries, 0)
        with self.assertRaises(ValueError):
            build_chat_model(SimpleNamespace(model_api_key='', model_name='test', model_base_url=''))

    def test_tracing_is_disabled_for_execution(self):
        from langsmith.run_helpers import get_tracing_context
        observed = []

        def reader(*args):
            observed.append(get_tracing_context().get('enabled'))
            return {'text': 'test'}

        model = ScriptedModel(responses=[call_file('skill://demo/SKILL.md'), AIMessage(content='done')])
        with patch.dict('os.environ', {'LANGSMITH_TRACING': 'true'}):
            events = self.run_model(model, reader)
        self.assertEqual(events[-1].type, 'done')
        self.assertEqual(observed, [False])

    def test_model_without_tool_support_fails_safely(self):
        class UnsupportedModel(ScriptedModel):
            def bind_tools(self, tools, **kwargs):
                raise NotImplementedError('FAKE_PROVIDER_DETAIL')

        events = self.run_model(UnsupportedModel(responses=[]), Mock())
        self.assertEqual(events[-1].type, 'error')
        self.assertNotIn('FAKE_PROVIDER_DETAIL', repr(events))

    def test_missing_tool_call_id_is_protocol_error(self):
        model = ScriptedModel(responses=[AIMessage(content='', tool_calls=[{
            'name': 'read_file', 'args': {'resource_uri': 'skill://demo/SKILL.md'}, 'id': None,
        }])])
        reader = Mock()
        events = self.run_model(model, reader)
        reader.assert_not_called()
        self.assertEqual(events[-1].type, 'error')


class AgentIntegrationTests(unittest.TestCase):
    def setUp(self):
        from python_backend.agents import AgentEngine
        self.storage = Mock()
        self.storage.save_question.return_value = 'question-id'
        self.storage.session_messages.side_effect = AssertionError('history must not be read')
        self.storage.conversation_file_id.side_effect = AssertionError('file history must not be read')
        self.task = threading.Event()
        self.tasks = Mock()
        self.tasks.register.return_value = self.task
        self.settings = SimpleNamespace(model_api_key='placeholder-test-key')
        self.skills = Mock()
        self.skills.select.side_effect = AssertionError('legacy selection must not run')
        self.skills.prompt_block.side_effect = AssertionError('eager loading must not run')
        self.session = Mock(descriptors=())
        self.skills.open_resource_session.return_value = self.session
        self.engine = AgentEngine(self.settings, self.storage, self.tasks, skills=self.skills)

    def test_skills_mode_has_no_history_and_preserves_existing_event_contract(self):
        model = ScriptedModel(responses=[AIMessage(content='技能回答')])
        with patch('python_backend.agents.build_chat_model', return_value=model):
            events = list(self.engine.stream('skills', 'conversation-id', '本次问题'))
        self.storage.session_messages.assert_not_called()
        self.storage.conversation_file_id.assert_not_called()
        self.skills.select.assert_not_called()
        self.skills.prompt_block.assert_not_called()
        self.assertEqual([message.type for message in model.requests[0]], ['system', 'human'])
        self.assertEqual(model.requests[0][-1].content, '本次问题')
        self.assertEqual([event['type'] for event in events], ['thinking', 'text', 'recommend', 'complete'])
        self.assertEqual(events[1]['content'], '技能回答')
        self.storage.update_answer.assert_called_once()
        self.tasks.remove.assert_called_once_with('conversation-id')

    def test_missing_model_does_not_load_or_echo_skill_body(self):
        self.settings.model_api_key = ''
        events = list(self.engine.stream('skills', 'conversation-id', '本次问题'))
        self.skills.open_resource_session.assert_not_called()
        self.assertEqual(events[-1]['type'], 'error')
        self.assertNotIn('complete', [event['type'] for event in events])
        self.storage.update_answer.assert_not_called()

    def test_current_question_only_on_each_request(self):
        for query in ('第一轮问题', '第二轮问题'):
            model = ScriptedModel(responses=[AIMessage(content='回答')])
            with patch('python_backend.agents.build_chat_model', return_value=model):
                list(self.engine.stream('skills', 'conversation-id', query))
            self.assertEqual([message.content for message in model.requests[0] if message.type == 'human'], [query])

    def test_failure_or_stop_never_emits_complete_or_saves_success(self):
        model = ScriptedModel(responses=[])
        with patch('python_backend.agents.build_chat_model', return_value=model):
            events = list(self.engine.stream('skills', 'conversation-id', '本次问题'))
        self.assertEqual(events[-1]['type'], 'error')
        self.storage.update_answer.assert_not_called()
        self.task.set()
        events = list(self.engine.stream('skills', 'conversation-id', '本次问题'))
        self.assertEqual(events[-1]['type'], 'error')
        self.assertNotIn('complete', [event['type'] for event in events])

    def test_non_skill_modes_keep_legacy_path(self):
        self.storage.session_messages.side_effect = None
        self.storage.session_messages.return_value = []
        self.storage.conversation_file_id.side_effect = None
        self.storage.conversation_file_id.return_value = None
        for mode in ('chat', 'file', 'deep', 'ppt'):
            with self.subTest(mode=mode), patch.object(self.engine, '_fallback', return_value=('旧模式回答', [])) as legacy:
                events = list(self.engine.stream(mode, 'conversation-id', '问题'))
                legacy.assert_called_once()
                self.assertEqual(events[-1]['type'], 'complete')
        self.skills.open_resource_session.assert_not_called()

    def test_end_to_end_real_registry_only_discloses_requested_content(self):
        from python_backend.skills import SkillRegistry
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'skills' / 'demo'
            package.mkdir(parents=True)
            (package / 'SKILL.md').write_text(
                '---\nname: demo\ndescription: 演示用途\n---\nBODY_SENTINEL', encoding='utf-8')
            (package / 'unused.md').write_text('UNUSED_SENTINEL', encoding='utf-8')
            registry = SkillRegistry(SimpleNamespace(repo_skills_dir=root / 'skills',
                skills_dir=root / 'installed', skill_catalog_db=root / 'catalog.db', skill_project='test'))
            uri = registry.open_resource_session('test').descriptors[0].entry_uri
            self.engine.skills = registry
            model = ScriptedModel(responses=[call_file(uri), AIMessage(content='已按读取的说明回答')])
            with patch('python_backend.agents.build_chat_model', return_value=model):
                events = list(self.engine.stream('skills', 'conversation-id', '请使用 demo'))
            self.assertEqual(events[-1]['type'], 'complete')
            self.assertNotIn('BODY_SENTINEL', repr(model.requests[0]))
            self.assertIn('BODY_SENTINEL', repr(model.requests[1]))
            self.assertNotIn('UNUSED_SENTINEL', repr(model.requests))
            self.assertNotIn(str(root), repr(model.requests))


if __name__ == '__main__':
    unittest.main()
