"""通用回答流程：证据落地后的提示组装、上下文装配与降级回答。"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from typing import Any, Generator

from python_backend.llm import model_ready
from python_backend.models import SessionMessage
from python_backend.modules.context_engineering.privacy import sanitize_text
from python_backend.modules.execution.trace import trace_preview
from python_backend.modules.skills.registry import Skill
from python_backend.modules.storage.relational import Storage


class AnswerFlowMixin:
    def _search(self, query: str) -> list[dict[str, str]]:
        key = self.settings.tavily_api_key
        if not key:
            return []
        payload = json.dumps({"api_key": key, "query": sanitize_text(query), "max_results": 5}).encode()
        request = urllib.request.Request("https://api.tavily.com/search", data=payload,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                results = json.loads(response.read().decode()).get("results", [])
            return [{"title": item.get("title", ""), "url": item.get("url", ""), "content": item.get("content", "")} for item in results]
        except Exception:
            return []

    def _fallback(self, agent: str, query: str, file_id: str | None = None,
                  history: list[SessionMessage] | None = None,
                  skill: Skill | None = None,
                  persona: dict[str, Any] | None = None,
                  emit_text: bool = False,
                  task: threading.Event | None = None,
                  conversation_id: str = '', source_id: str = '',
                  workspace_rules: str = '', workspace_id: str = '',
                  clarified: bool = False, scope_key: str = '') -> Generator[dict[str, Any], None, tuple[str, list[dict[str, str]], bool]]:
        context = ""
        grounded = False
        route = ""
        if file_id:
            context, grounded, route = yield from self._grounding(file_id, query, workspace_id)
        elif workspace_id:
            # 没有选中文档时，工作区召回是唯一的落地材料。
            hits = self._workspace_evidence(workspace_id, query)
            if hits:
                context = "\n\n".join(hits)
                grounded = True
                route = "workspace"
        # 需求分析机器人先判需求说不说不清：说不清就先给三个理解方向。
        requirement_mode = self._requirement_mode(persona)
        requirement = (self._requirement_gate(agent, query, file_id, history, clarified)
                       if requirement_mode else None)
        if requirement is not None:
            yield self.step('clarify', '需求信息不足，先确认方向', status='completed')
            yield self.event('clarify', requirement.to_dict(), stage='clarify')
            return "", [], True
        # Gate: when the intent is not confident enough, ask the user to clarify
        # instead of answering the wrong question.
        gate = None if requirement_mode else self._intent_gate(agent, sanitize_text(query), file_id)
        if gate is not None:
            request, candidates = gate
            yield self.step('clarify', '需要确认需求方向', status='completed')
            yield self.event('clarify', request.to_dict(), stage='clarify')
            return "", [], True
        context = yield from self._expand_evidence(query, context, workspace_id, file_id, task, force=agent == 'deep')
        # A file-grounded answer must not fall through to web search, otherwise an
        # ambiguous follow-up gets answered with unrelated search results.
        # Same for a matched skill: the SKILL.md definitions govern the answer.
        web_agent = ((agent in {"chat", "deep"} and not requirement_mode)
                     or (agent == "skills" and not skill))
        refs = []
        if not context and web_agent and not grounded:
            if self.settings.tavily_api_key:
                yield self.step('web_search', '正在搜索网络资料', status='running')
            refs = self._search(query)
            if self.settings.tavily_api_key:
                titles = [trace_preview(str(item.get('title') or '参考资料'), 180)[0] for item in refs]
                yield self.step('web_search', f'已找到 {len(refs)} 条参考资料', documents=titles)
        system = "你是 Hotline Agent，请用中文给出准确、结构清晰的回答。"
        if skill and self.skills:
            system = f"{self.skills.prompt_block(skill)}\n\n{system}"
        system = self._persona_block(persona, system)
        if workspace_rules:
            system += '\n\n当前工作区规则\n' + workspace_rules
        messages = [{"role": "system", "content": system}]
        for turn in history or []:
            messages.append({"role": "user", "content": turn.question})
            if turn.answer:
                messages.append({"role": "assistant", "content": turn.answer[:1500]})
        model_prompt = query
        if context:
            model_prompt = f"本次选择的召回链路：{route}\n请基于以下知识库内容回答问题：\n{context}\n\n问题：{query}"
        if refs:
            model_prompt += "\n\n搜索结果：\n" + "\n".join(f"{r['title']}: {r['content']}" for r in refs)
        messages.append({"role": "user", "content": model_prompt})
        manifest = {}
        if self.context and conversation_id:
            preparation_events = []
            def prepare_chat(inputs):
                preparation_events.append(self._context('context-preparation', inputs))
                return self.model.chat(inputs)
            if model_ready(self.settings):
                self.context.extract_state(scope_key or conversation_id, source_id, prepare_chat)
            self.context.checkpoint(scope_key or conversation_id, history or [], prepare_chat if model_ready(self.settings) else None)
            yield from preparation_events
            older_matches = (self.storage.search_session_messages(conversation_id, query)
                             if isinstance(self.storage, Storage) else [])
            evidence = context
            if refs:
                evidence += '\n' + '\n'.join(f"{item['title']}\n{item['content']}" for item in refs)
            yield self.step('context', '正在恢复任务状态、召回记忆并检查输入预算', status='running')
            messages, manifest = self.context.prepare(scope_key or conversation_id, system, query, (history or [])[-4:],
                                                       evidence, extra_history=older_matches)
            yield self.step('context', '上下文装配完成', **manifest)
        yield self.step('llm', '正在组织回答', status='running')
        yield self._context('answer', messages, {'fileId': file_id, 'grounded': grounded,
                            'retrievalRoute': route, 'historyIds': [str(turn.id) for turn in history or []],
                            'referenceCount': len(refs), 'context': manifest})
        started = time.monotonic()
        if emit_text:
            pieces: list[str] = []
            for piece in self.model.stream(messages):
                if task is not None and task.is_set():
                    break
                pieces.append(piece)
                yield self.event('text', piece)
            answer = ''.join(pieces)
            if not answer:
                # 上游不支持流式时退回一次性结果
                answer = self.model.chat(messages)
                if answer:
                    yield self.event('text', answer)
        else:
            answer = self.model.chat(messages)
        yield self.step('llm', '回答已生成', int((time.monotonic() - started) * 1000), outputChars=len(answer or ''))
        usage = self._usage_event()
        if usage:
            yield usage
        if not answer:
            if agent == "ppt":
                answer = f"已解析 PPT 需求：{query}\n将按模板生成演示文稿。"
            elif context:
                answer = f"模型未生成回答，以下为本地召回的原文证据。\n\n问题 {query}\n\n{context[:3000]}"
            elif skill and self.skills:
                answer = (f"已匹配技能「{skill.name}」，但当前未配置大模型，无法按技能执行。\n\n"
                          f"{self.skills.prompt_block(skill)[:3000]}")
            elif refs:
                answer = "根据联网搜索结果：\n" + "\n".join(f"- {r['title']}：{r['content'][:300]}" for r in refs)
            else:
                answer = f"已收到问题：{query}\n当前未配置外部大模型，已使用本地降级模式。"
            if emit_text:
                yield self.event('text', answer)
        return answer, refs, False
