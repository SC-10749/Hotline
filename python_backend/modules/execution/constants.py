"""执行链路共享常量：门闸标记、需求交接标记与推荐项文案。"""

# 门闸触发时写进会话记录的标记：下一轮若是这段追问的回答，就不再重复追问。
CLARIFY_FLAG = '需要澄清'
# 绑定了这个技能的机器人走需求分析流程：先判需求说不说不清，再谈产出。
REQUIREMENT_SKILL = 'requirement-analysis'
# 需求正文标记：写进会话记录的 thinking，交接时据此找到最近一次需求条目。
REQUIREMENT_FLAG = '需求条目'
# 交接给技能的需求正文长度上限：够放下验收条件，又不把提示撑爆。
REQUIREMENT_BRIEF_CHARS = 8000
# 推荐项文案与目标技能由交接模块统一提供，模型层序列化历史数据时也用它。
from python_backend.modules.skills.handoff import TDD_RECOMMENDATION, TDD_SKILL  # noqa: E402
