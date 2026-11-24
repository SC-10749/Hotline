"""本地数据种子：把仓库技能包装进 data/skills，登记机器人及其工具项。

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

# 角色机器人：与需求分析助手同一个人设机制，只有名字、绑定技能和角色指令不同。
# 提示词保持短句，缺信息就问、不替用户补默认值。
ROLE_BOTS: tuple[dict[str, object], ...] = (
    {
        'name': '产品经理',
        'skills': ['requirement-analysis'],
        'instruction': (
            '你是一名产品经理。结论先行，把用户的话翻译成可验收的需求条目；'
            '信息不够就一句话点出卡在哪，一轮最多问 3 个问题，每题给 2 到 4 个候选答案；'
            '不替用户补默认值，不确定就写 NEEDS CLARIFICATION。只输出中文。'
        ),
    },
    {
        'name': '前端工程师',
        'skills': [],
        'instruction': (
            '你是一名前端工程师。给能直接落地的组件代码与样式：先说改哪个文件，再说怎么改；'
            '沿用项目现有的组件、变量和写法，不擅自引入新依赖；顺带说明窄屏与深浅色下的表现。'
            '只输出中文。'
        ),
    },
    {
        'name': '后端工程师',
        'skills': [],
        'instruction': (
            '你是一名后端工程师。先给接口契约（方法、字段、错误码）和数据模型，再讲实现要点；'
            '主动考虑事务、并发、幂等与向后兼容；不臆造项目里没有的依赖或中间件。只输出中文。'
        ),
    },
    {
        'name': 'AI 工程师',
        'skills': [],
        'instruction': (
            '你是一名 AI 工程师。先给方案和评估口径（数据集、基线、指标），再讲实现；'
            '把已知事实和假设分开写，不编造指标数字；给出效果不及预期时的回退方案。只输出中文。'
        ),
    },
    {
        'name': '运维工程师',
        'skills': [],
        'instruction': (
            '你是一名运维工程师。先说影响面和回滚方案，再给逐步命令；'
            '每一步配一个可验证的检查点；删数据、改配置、重启这类高风险操作单独标出来。'
            '只输出中文。'
        ),
    },
    {
        'name': '测试工程师',
        'skills': ['hotline-tdd'],
        'instruction': (
            '你是一名测试工程师。先给测试清单和验收条件，再给用例（Given/When/Then）；'
            '覆盖正常、边界、异常与回滚场景；缺信息就写 NEEDS CLARIFICATION，不自己编需求。'
            '只输出中文。'
        ),
    },
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


def _upsert_bot(store: BotStore, payload: dict, enabled_default: bool) -> dict:
    """按名称更新或新建机器人；已有机器人保留用户设置的开启状态。"""
    existing = next((bot for bot in store.list() if bot['name'] == payload['name']), None)
    body = dict(payload)
    body['enabled'] = existing['enabled'] if existing else enabled_default
    if existing:
        return store.update(existing['bot_id'], body)
    return store.create(body)


def seed(settings: Settings | None = None) -> dict:
    """安装仓库技能包、登记机器人与工具登记项。"""
    settings = settings or Settings()
    settings.ensure_dirs()
    registry = SkillRegistry(settings)
    installed = install_repo_skills(settings, registry)
    skill = installed.get(SKILL_NAME) or registry.install_from_dir(settings.repo_skills_dir / SKILL_NAME)
    store = BotStore(settings.data_dir / BOT_DB_NAME)
    main_bot = _upsert_bot(store, {'name': BOT_NAME, 'instruction': INSTRUCTION,
                                   'skills': [skill.id]}, enabled_default=True)
    role_bots = []
    for role in ROLE_BOTS:
        skill_ids = [installed[name].id for name in role['skills'] if name in installed]
        role_bots.append(_upsert_bot(store, {'name': role['name'],
                                             'instruction': role['instruction'],
                                             'skills': skill_ids}, enabled_default=False))
    tool = register_agent_tool(settings, main_bot['bot_id'])
    return {'skill': skill.to_dict(), 'skills': sorted(installed), 'bot': main_bot,
            'role_bots': role_bots, 'tool': tool}


if __name__ == '__main__':
    result = seed()
    print(f"技能：{result['skill']['name']}（{result['skill']['id']}）")
    print(f"已安装仓库技能：{'、'.join(result['skills'])}")
    print(f"机器人：{result['bot']['name']}（{result['bot']['bot_id']}），绑定技能 {result['bot']['skills']}")
    for bot in result['role_bots']:
        print(f"角色机器人：{bot['name']}（{bot['bot_id']}），绑定技能 {bot['skills']}")
    print(f"工具登记：{result['tool']['name']}（{result['tool']['tool_id']}），来源 {result['tool']['source']}")
