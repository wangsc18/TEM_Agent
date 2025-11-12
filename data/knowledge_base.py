#!/usr/bin/env python3
"""
知识库管理器 - 管理航空专业知识文档
"""
import os
from pathlib import Path
from typing import Dict, List, Optional


class KnowledgeBase:
    """知识库管理器"""

    def __init__(self, kb_dir: str = "knowledge_base"):
        """
        初始化知识库

        Args:
            kb_dir: 知识库目录路径
        """
        self.kb_dir = Path(kb_dir)
        self.documents: Dict[str, str] = {}
        self._load_all_documents()

    def _load_all_documents(self):
        """加载所有知识库文档"""
        if not self.kb_dir.exists():
            print(f"[知识库] 警告: 知识库目录 {self.kb_dir} 不存在")
            return

        # 遍历所有.txt和.md文件
        for file_path in self.kb_dir.glob("**/*"):
            if file_path.is_file() and file_path.suffix in [".txt", ".md"]:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        # 使用相对路径作为key
                        rel_path = file_path.relative_to(self.kb_dir)
                        doc_name = str(rel_path.with_suffix(""))  # 去掉扩展名
                        self.documents[doc_name] = content
                        print(f"[知识库] 已加载: {doc_name}")
                except Exception as e:
                    print(f"[知识库] 加载失败 {file_path}: {e}")

        print(f"[知识库] 共加载 {len(self.documents)} 个文档")

    def get_document(self, doc_name: str) -> Optional[str]:
        """
        获取指定文档内容

        Args:
            doc_name: 文档名称（不含扩展名）

        Returns:
            文档内容，如果不存在返回None
        """
        return self.documents.get(doc_name)

    def search_documents(self, keywords: List[str]) -> Dict[str, str]:
        """
        搜索包含关键词的文档

        Args:
            keywords: 关键词列表

        Returns:
            匹配的文档字典 {文档名: 内容}
        """
        results = {}
        for doc_name, content in self.documents.items():
            # 检查是否包含任一关键词
            if any(keyword.lower() in content.lower() for keyword in keywords):
                results[doc_name] = content

        return results

    def get_all_documents(self) -> Dict[str, str]:
        """
        获取所有文档

        Returns:
            所有文档的字典 {文档名: 内容}
        """
        return self.documents.copy()

    def list_documents(self) -> List[str]:
        """
        列出所有文档名称

        Returns:
            文档名称列表
        """
        return list(self.documents.keys())

    def format_for_llm(self, doc_names: Optional[List[str]] = None) -> str:
        """
        格式化文档内容供LLM使用

        Args:
            doc_names: 要包含的文档名称列表，None表示包含所有文档

        Returns:
            格式化后的文本
        """
        if doc_names is None:
            doc_names = self.list_documents()

        formatted_parts = []
        formatted_parts.append("=== 专业知识库 ===\n")

        for doc_name in doc_names:
            content = self.get_document(doc_name)
            if content:
                formatted_parts.append(f"\n【{doc_name}】")
                formatted_parts.append(content)
                formatted_parts.append("\n" + "="*50)

        return "\n".join(formatted_parts)


# 全局知识库实例（延迟初始化）
_global_kb: Optional[KnowledgeBase] = None


def get_knowledge_base(kb_dir: str = "knowledge_base") -> KnowledgeBase:
    """
    获取全局知识库实例（单例模式）

    Args:
        kb_dir: 知识库目录路径

    Returns:
        KnowledgeBase实例
    """
    global _global_kb
    if _global_kb is None:
        _global_kb = KnowledgeBase(kb_dir)
    return _global_kb
