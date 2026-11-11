from __future__ import annotations

import io
from pathlib import Path


def parse_file(path: Path, max_length: int = 20000) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json", ".xml", ".html"}:
        full = path.read_text(encoding="utf-8", errors="replace").strip()
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
            full = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages).strip()
        except Exception as exc:
            raise ValueError(f"PDF 解析失败: {exc}") from exc
    elif suffix == ".docx":
        try:
            from docx import Document
            full = "\n".join(p.text for p in Document(str(path)).paragraphs if p.text.strip()).strip()
        except Exception as exc:
            raise ValueError(f"DOCX 解析失败: {exc}") from exc
    elif suffix in {".png", ".jpg", ".jpeg"}:
        full = "图片文件已上传。当前运行模式未配置 OCR 服务，请通过模型服务进行图像问答。"
    else:
        raise ValueError(f"不支持的文件类型: {suffix or 'unknown'}")
    truncated = full if len(full) <= max_length else full[:max_length] + "\n\n... (内容已截断，文件过长)"
    return full, truncated
