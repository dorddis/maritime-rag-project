"""
Maritime RAG System

Hybrid RAG combining:
- Text-to-SQL for structured queries
- Vector search for semantic queries
- Real-time Redis data integration
"""

from .config import settings

__all__ = ["settings"]
