from __future__ import annotations

from uuid import uuid4
from collections.abc import Iterator

from typing import Any

from python_backend.config import Settings
from python_backend.modules.execution.grounding import GroundingMixin
from python_backend.modules.execution.model_client import ModelClient
from python_backend.modules.execution.tasks import TaskManager
from python_backend.modules.execution.gates import GateMixin
from python_backend.modules.execution.answer_flow import AnswerFlowMixin
from python_backend.modules.execution.skill_flow import SkillFlowMixin
from python_backend.modules.execution.trace import trace_preview
from python_backend.modules.context_engineering.snapshots import context_snapshot
from python_backend.modules.context_engineering.privacy import sanitize_value, sanitize_text
from python_backend.modules.context_engineering.service import ContextService
from python_backend.modules.intent import ACTION_CATALOG, DecisionClient, ExampleVectorStore, RETRIEVAL_CATALOG, decision_config_from_settings, vector_config_from_settings
from python_backend.llm import model_ready
from python_backend.modules.skills.registry import SkillRegistry
from python_backend.modules.storage.relational import Storage
from python_backend.modules.retrieval.vector_store import PgVectorStore

from python_backend.modules.execution.constants import CLARIFY_FLAG, REQUIREMENT_FLAG, TDD_RECOMMENDATION, TDD_SKILL


class AgentEngine(GroundingMixin, GateMixin, AnswerFlowMixin, SkillFlowMixin):
    HISTORY_TURNS = 4
    # 意图置信度低于该值时先向用户澄清，不直接作答。
    INTENT_GATE = 0.6

    def __init__(self, settings: Settings, storage: Storage, tasks: TaskManager, vector_store: PgVectorStore | None = None,
                 skills: SkillRegistry | None = None, documents=None, persona_reader=None, context_service=None,
                 workspace_rules_reader=None, workspace_recall=None, workspace_source_reader=None):
        self.settings, self.storage, self.tasks = settings, storage, tasks
        self.vector_store = vector_store
        self.skills = skills
        self.documents = documents
        self.model = ModelClient(settings)
        # 第二层：意图示例的向量缓存。未配置 embedding 时自动跳过该层。
        _vector_config = vector_config_from_settings(settings)
        self.intent_vectors = ExampleVectorStore(RETRIEVAL_CATALOG, _vector_config)
        self.action_vectors = ExampleVectorStore(ACTION_CATALOG, _vector_config)
        # 决策层：一次前向给出意图与诉求歧义度。未配置则不启用，
        # 意图级联照旧走大模型判定。
        self.decision = DecisionClient(decision_config_from_settings(settings))
        # 人设读取器由 Worker 注入；未注入时对话使用默认提示词。
        self.persona_reader = persona_reader
        self.workspace_rules_reader = workspace_rules_reader
        # 工作区级关键词召回由 Worker 注入；未注入时检索范围仍限单个文档。
        self.workspace_recall = workspace_recall
        self.workspace_source_reader = workspace_source_reader
        self.context = context_service
        if self.context is None and getattr(settings, 'context_enabled', True) and getattr(settings, 'data_dir', None):
            self.context = ContextService(settings)

    def _persona(self, conversation_id: str) -> dict[str, Any]:
        if not callable(self.persona_reader):
            return {}
        try:
            return self.persona_reader(conversation_id) or {}
        except Exception:
            return {}

    @staticmethod
    def event(event_type: str, content: Any = "", **extra: Any) -> dict[str, Any]:
        result = {"type": event_type, "content": content}
        result.update(extra)
        return result

    @staticmethod
    def step(stage: str, content: str, duration_ms: int | None = None, *,
             status: str = 'completed', **details: Any) -> dict[str, Any]:
        """阶段事件：只放阶段名、耗时与计数，不放原文与凭据。"""
        result = {"type": "step", "stage": stage, "content": content, "status": status}
        if duration_ms is not None:
            result["durationMs"] = duration_ms
        if details:
            result["details"] = details
        return result

    def _persona_block(self, persona: dict[str, Any] | None, system: str) -> str:
        """机器人角色指令、绑定技能与个人回答风格只在系统提示词里追加，不覆盖既有规则。"""
        if not persona:
            return system
        parts: list[str] = []
        instruction = str(persona.get('instruction') or '').strip()
        if instruction:
            parts.append(f"你正在扮演以下角色，请严格按照它回答：\n{instruction}")
        for skill_id in persona.get('skills') or []:
            skill = self.skills.get(skill_id) if self.skills else None
            if skill:
                parts.append(self.skills.prompt_block(skill))
        style = str(persona.get('style') or '').strip()
        if style:
            parts.append(style)
        return f"{system}\n\n" + "\n\n".join(parts) if parts else system


    def _usage_event(self) -> dict[str, Any] | None:
        """把最近一次模型调用的 token 用量转成事件，取不到就不发。"""
        usage = getattr(self.model, 'last_usage', None)
        if not usage:
            return None
        return self.event('usage', '模型用量', usage=dict(usage))

    def _context(self, stage: str, messages: list, sources: dict | None = None) -> dict:
        return context_snapshot(stage, sanitize_value(messages), model_name=getattr(self.settings, 'model_name', ''),
                                model_configured=model_ready(self.settings), sources=sources)


    def _remember_answer(self, conversation_id: str, source_id: str, query: str, answer: str):
        if self.context is None or not conversation_id:
            return None
        try:
            self.context.complete(conversation_id, source_id, query, answer)
        except Exception:
            return self.step('memory_write', '回答已保存，上下文保存失败，请检查本地存储', status='failed')
        return self.step('memory_write', '已保存本轮任务上下文')

    def stream(self, agent: str, conversation_id: str, query: str, file_id: str | None = None,
               *, workspace_id: str = '', run_id: str = '', workspace_root: str = '',
               task_key: str = '', persist_history: bool = True) -> Iterator[dict[str, Any]]:
        if agent == 'chat' and self._is_tdd_handoff(query):
            # 交接口令只由后端认定：前端漏切模式时，这一轮照样按技能流执行。
            agent = 'skills'
        # 子任务用独立任务键注册：同一会话的多个子任务不共用一把锁。
        task = self.tasks.register(task_key or conversation_id)
        # 上下文与记忆按任务键隔离：子任务不写父会话的记忆状态，
        # 也不会因为共用会话作用域而撞上乐观锁。
        scope_key = task_key or conversation_id
        persona = self._persona(conversation_id)
        if persist_history:
            row_id = self.storage.save_question(conversation_id, query, agent, file_id)
        else:
            # 子任务不写会话历史：父会话保持干净，产出只进事件流与记忆。
            row_id = f"sub-{run_id or uuid4().hex[:12]}"
        thinking: list[str] = []
        try:
            # 告诉前端这一轮实际跑的是哪个助手：前端据此切模式，底部输入区跟着换形态。
            yield self.event('agent', agent)
            yield self.event('thinking', '正在理解问题', stage='understanding', status='running')
            if task.is_set():
                yield self.event("error", "任务已停止")
                return
            workspace_rules = self._read_workspace_rules(workspace_id, workspace_root)
            messages = (self.storage.context_messages(conversation_id) if self.context and isinstance(self.storage, Storage)
                        else self.storage.session_messages(conversation_id))
            history = [row for row in messages
                       if row.id != row_id and row.answer]
            if agent == 'skills' and self.context is None:
                yield from self._stream_skills(query, row_id, task, scope_key, history,
                                               workspace_rules=workspace_rules,
                                               workspace_id=workspace_id, file_id=file_id)
                return
            if not file_id and agent != 'ppt':
                file_id = self.storage.conversation_file_id(conversation_id)
            # 上一轮是澄清门闸时，本轮是用户在回答澄清，不再重复追问同一件事。
            previous = next((row for row in reversed(messages) if row.id != row_id), None)
            clarified = bool(previous) and CLARIFY_FLAG in str(getattr(previous, 'thinking', '') or '')
            if self.context:
                self.context.begin(scope_key, workspace_id, str(row_id), query, history)
            else:
                history = history[-self.HISTORY_TURNS:]
            if agent == 'skills':
                yield from self._stream_skills(query, row_id, task, scope_key, history, workspace_rules,
                                               workspace_id=workspace_id, file_id=file_id)
                return
            if agent == "deep":
                yield self.step('research', '正在准备检索任务', status='running')
            elif agent == "ppt":
                yield self.step('ppt_plan', '正在整理演示内容', status='running')
            elif agent == "file" or file_id:
                source = (self.storage.get_file(file_id) or self.storage.get_document(file_id)) if file_id else None
                name = str(getattr(source, 'fileName', '') or '').replace('\\', '/').rsplit('/', 1)[-1]
                name = trace_preview(name, 180)[0]
                label = f'正在检索《{name}》' if name else '正在检索所选文档'
                yield self.step('retrieval_request', label, status='running')
            answer, refs, gated = yield from self._fallback(
                agent, query, file_id, history, persona=persona, emit_text=True,
                task=task, conversation_id=conversation_id, source_id=str(row_id),
                workspace_rules=workspace_rules, workspace_id=workspace_id,
                clarified=clarified, scope_key=scope_key)
            if task.is_set():
                yield self.event("error", "任务已停止")
                return
            if gated:
                # 下一轮将用户作答重新送入分类级联。
                self.storage.update_answer(row_id, "", CLARIFY_FLAG, "", None, None)
                yield self.event("complete", "")
                return
            if refs:
                yield self.event("reference", refs, count=len(refs))
            recommendations = [f"请进一步解释：{query}", "给出一个实际案例"]
            requirement_mode = self._requirement_mode(persona)
            if requirement_mode:
                # 结构化推荐项：前端按 skill 字段切到技能助手，标签文案只由后端定义。
                recommendations.append({'label': TDD_RECOMMENDATION, 'skill': TDD_SKILL})
            yield self.event("recommend", recommendations)
            record = "\n".join(thinking)
            if requirement_mode:
                record = f"{record}\n{REQUIREMENT_FLAG}"
            self.storage.update_answer(row_id, answer, record, "", refs, recommendations)
            memory_event = self._remember_answer(scope_key, str(row_id), query, answer)
            if memory_event:
                yield memory_event
            yield self.event("complete", "")
        except Exception as exc:
            self.storage.update_answer(row_id, "", "", "", None, None)
            yield self.event("error", sanitize_text(str(exc)))
        finally:
            self.tasks.remove(conversation_id)

