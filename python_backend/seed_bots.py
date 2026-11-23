"""本地数据种子：把仓库技能包装进 data/skills，登记「需求分析助手」机器人及其工具项。

用法：python -m python_backend.seed_bots
可重复执行：技能包原地更新（机器人绑定的技能编号不变），机器人按名称更新，
工具登记按名称更新，都不产生重复记录。
"""

from __future__ import annotations

from python_backend.config import Settings
from python_backend.infrastructure.bot_store import BotStore
from python_backend.infrastructure.persona import BOT_DB_NAME
from python_backend.infrastructure.registry_store import RegistryStore
from python_backend.modules.execution.agent_tool import AGENT_SOURCE
from python_backend.modules.execution.tools import REGISTRY_DB_NAME
from python_backend.modules.skills.registry import Skill, SkillRegistry

BOT_NAME = '需求分析助手'
SKILL_NAME = 'requirement-analysis'
TOOL_NAME = 'requirement_analysis'
TOOL_DESCRIPTION = ('把一段需求描述变成可验收的结构化需求；需求说不清时返回三个澄清方向，'
                     '把用户对上一轮澄清的回答放进 clarification 参数再调用一次。'
                     '调用前先用 read_skill 读取 requirement-analysis 技能说明。')
TOOL_SCHEMA = {
    'type': 'object',
    'properties': {
        'query': {'type': 'string', 'description': '待交给该智能体处理的原始需求描述'},
        'clarification': {'type': 'string', 'description': '用户对上一轮澄清的回答；为空表示首次提问'},
    },
    'required': ['query'],
}
INSTRUCTION = (
    '你是一名资深需求分析师。说话像同事，不像文档模板：结论先行、短句、说人话，'
    '不拿「诊断 / 约束清单 / 追踪矩阵」当标题。'
    '收到需求先判断信息够不够写出可验收的条目：目标用户、核心范围或验收标准说不清时，'
    '先用一句白话说明这条需求卡在哪，再一轮最多 3 个问题，每个问题给 2 到 4 个候选答案，'
    '不写「为什么问」小作文；'
    '信息足够时先给不超过 10 行的结论（问题是什么 / V1 做什么 / 不做什么 / 还差什么没定），'
    '再展开用户故事（带 Given/When/Then）、FR、NFR、成功标准、V1 范围、假设与未决问题。'
    '不猜测、不替用户补默认值，不确定就写 NEEDS CLARIFICATION 或列为显式假设。只输出中文。'
)


def register_agent_tool(settings: Settings, bot_id: str) -> dict:
    """把机器人登记为工具：登记项的 input_schema.agent 指向机器人编号。"""
    registry = RegistryStore(settings.data_dir / REGISTRY_DB_NAME)
    schema = dict(TOOL_SCHEMA)
    schema['agent'] = {'bot_id': bot_id}
    payload = {'name': TOOL_NAME, 'source': AGENT_SOURCE, 'scope': 'workspace', 'risk': 'low',
               'status': 'configured', 'description': TOOL_DESCRIPTION,
               'input_schema': schema, 'approval_policy': 'risk-based'}
    existing = next((row for row in registry.list_tools() if row.get('name') == TOOL_NAME), None)
    if existing:
        return registry.update_tool(existing['tool_id'], payload, existing['revision'])
    return registry.create_tool(payload)


def install_repo_skills(settings: Settings, registry: SkillRegistry) -> dict[str, Skill]:
    """把仓库里所有技能包装进 data/skills：同名原地更新，编号不变。"""
    installed: dict[str, Skill] = {}
    root = settings.repo_skills_dir
    if not root.is_dir():
        return installed
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and (entry / 'SKILL.md').is_file():
            item = registry.install_from_dir(entry)
            installed[item.name] = item
    return installed


def seed(settings: Settings | None = None) -> dict:
    """安装仓库技能包、登记机器人与工具登记项。"""
    settings = settings or Settings()
    settings.ensure_dirs()
    registry = SkillRegistry(settings)
    installed = install_repo_skills(settings, registry)
    skill = installed.get(SKILL_NAME) or registry.install_from_dir(settings.repo_skills_dir / SKILL_NAME)
    store = BotStore(settings.data_dir / BOT_DB_NAME)
    payload = {'name': BOT_NAME, 'instruction': INSTRUCTION,
               'skills': [skill.id], 'enabled': True}
    existing = next((bot for bot in store.list() if bot['name'] == BOT_NAME), None)
    bot = store.update(existing['bot_id'], payload) if existing else store.create(payload)
    tool = register_agent_tool(settings, bot['bot_id'])
    return {'skill': skill.to_dict(), 'skills': sorted(installed), 'bot': bot, 'tool': tool}


if __name__ == '__main__':
    result = seed()
    print(f"技能：{result['skill']['name']}（{result['skill']['id']}）")
    print(f"已安装仓库技能：{'、'.join(result['skills'])}")
    print(f"机器人：{result['bot']['name']}（{result['bot']['bot_id']}），绑定技能 {result['bot']['skills']}")
    print(f"工具登记：{result['tool']['name']}（{result['tool']['tool_id']}），来源 {result['tool']['source']}")
