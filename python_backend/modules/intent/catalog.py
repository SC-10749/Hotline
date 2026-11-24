"""意图目录：把用户输入映射到少量稳定动作。

每个意图描述三件事——标识、给模型的说明、命中用的关键词。关键词只做第一阶段
粗筛（毫秒级、无模型调用），模型只在粗筛结果模糊时做最终判定。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Intent:
    """一个可路由的意图。"""

    name: str
    label: str
    description: str
    keywords: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()

    def prompt_block(self) -> str:
        lines = [f'- {self.name}（{self.label}）：{self.description}']
        if self.examples:
            lines.append('  例如：' + '；'.join(self.examples))
        return '\n'.join(lines)


@dataclass(frozen=True)
class IntentCatalog:
    """一组意图及其默认意图。"""

    name: str
    intents: tuple[Intent, ...]
    default: str
    aliases: dict[str, str] = field(default_factory=dict)

    def names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.intents)

    def get(self, name: str) -> Intent | None:
        return next((item for item in self.intents if item.name == name), None)

    def resolve(self, name: str) -> str | None:
        """把模型输出的名称归一化：接受别名、大小写和连字符差异。"""
        if not name:
            return None
        key = name.strip().lower().replace('-', '_').replace(' ', '_')
        if key in self.aliases:
            return self.aliases[key]
        for item in self.intents:
            if item.name.lower() == key:
                return item.name
        return None

    def prompt_block(self) -> str:
        return '\n'.join(item.prompt_block() for item in self.intents)


# 检索链路：决定知识库查询走哪条召回路径。
RETRIEVAL_CATALOG = IntentCatalog(
    name='retrieval',
    default='hybrid',
    intents=(
        Intent('semantic', '语义检索',
               '概念或语义相近的问题，例如“它的原理是什么”“这两者有什么区别”',
               keywords=('原理', '区别', '为什么', '是什么', '含义', '机制'),
               examples=('向量检索和全文检索有什么区别', 'SSE 的原理是什么')),
        Intent('keyword', '关键词检索',
               '专有名词、错误码、编号或需要精确短语匹配的问题',
               keywords=('错误码', '报错', 'code', 'api', '接口', '字段', '参数'),
               examples=('ERR_CONNECTION_REFUSED 怎么处理', 'fileId 字段在哪里定义')),
        Intent('text2sql', '文档查询',
               '对文档内容做数量、列表或条件筛选的问题',
               keywords=('多少', '数量', '统计', '列表', '总数', '有哪些'),
               examples=('这份文档有多少条记录', '统计一下出现过哪些关键词')),
        Intent('graph', '关联检索',
               '实体之间的依赖、归属或上下游关系',
               keywords=('关系', '依赖', '关联', '上下游', '谁负责', '属于'),
               examples=('模块之间有什么依赖', '这个组件属于哪个模块')),
        Intent('hybrid', '综合检索',
               '无法确定单一路径，或需要语义与关键词混合召回',
               keywords=(),
               examples=('介绍一下这个项目', '随便聊聊')),
    ),
)

# 顶层动作：决定一次提问应该由哪个 Agent 处理。
ACTION_CATALOG = IntentCatalog(
    name='action',
    default='chat',
    intents=(
        Intent('file', '文件问答',
               '针对已上传文件或知识库内容提问',
               keywords=('文档', '文件', '这份', '附件', 'pdf', 'word', '报告里', '资料'),
               examples=('这份报告里说了什么', '附件中的合同到期时间')),
        Intent('ppt', 'PPT 生成',
               '要求制作、整理或修改演示文稿',
               keywords=('ppt', '幻灯片', '演示文稿', 'slides', '做个汇报'),
               examples=('把这份内容做成 PPT', '生成一个产品介绍幻灯片')),
        Intent('deep', '深度研究',
               '需要检索、多轮分析和综合论证的复杂问题',
               keywords=('调研', '深入', '研究', '分析对比', '综述', '报告深度'),
               examples=('调研一下向量数据库的选型', '深入分析这条链路的成本')),
        Intent('skills', '技能助手',
               '调用已安装技能包完成的工作流任务',
               keywords=('用技能', '技能', '按流程', 'skill', '工作流'),
               examples=('用复盘技能整理这次故障', '按测试流程跑一遍')),
        Intent('chat', '对话助手',
               '通用问答、解释、写作等不需要额外执行器的请求',
               keywords=('解释', '什么是', '怎么写', '推荐', '总结'),
               examples=('解释一下索引的作用', '帮我写一段介绍文案')),
    ),
)