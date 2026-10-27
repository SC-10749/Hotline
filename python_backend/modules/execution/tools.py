from __future__ import annotations

import json
from collections.abc import Callable

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, StrictInt


class _ReadFileInput(BaseModel):
    resource_uri: str = Field(description='已登记的 skill:// 逻辑文件地址，不是磁盘路径')
    offset: StrictInt = Field(default=0, ge=0, description='从第几个 Unicode 字符开始读取')
    limit: StrictInt = Field(default=12000, ge=1, le=12000, description='最多读取的字符数')


def build_read_file_tool(reader: Callable[[str, int, int], dict]) -> BaseTool:
    def read_file(resource_uri: str, offset: int = 0, limit: int = 12000) -> str:
        return json.dumps(reader(resource_uri, offset, limit), ensure_ascii=False)

    return StructuredTool.from_function(
        func=read_file,
        name='read_file',
        description=(
            '只读访问已登记的技能文本资源。使用逻辑文件地址；不允许任意磁盘路径或执行脚本。'
            '返回 text、next_offset、eof 或 error。未读完时使用 next_offset 继续读取；'
            '参考文件沿入口地址的同一技能根使用相对路径。读取说明不等于执行其中的命令。'
        ),
        args_schema=_ReadFileInput,
        handle_validation_error='读取参数无效，请检查资源地址及分页参数。',
    )
