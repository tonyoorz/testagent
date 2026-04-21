from datetime import datetime
from typing import Any, Dict, List, Optional


class QueryMemory:
    def __init__(self, max_entries: int = 20):
        self.max_entries = max(1, int(max_entries))
        self._entries: List[Dict[str, Any]] = []

    def add_query(
        self,
        question: str,
        *,
        answer: str = '',
        intents: Optional[List[str]] = None,
        trace: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._entries.append(
            {
                'question': str(question or '').strip(),
                'answer': str(answer or '').strip(),
                'intents': list(intents or []),
                'trace': dict(trace or {}),
                'metadata': dict(metadata or {}),
                'timestamp': datetime.now().isoformat(),
            }
        )
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]

    def list_entries(self) -> List[Dict[str, Any]]:
        return [dict(entry) for entry in self._entries]

    def build_prompt_context(self, max_chars: int = 1200) -> str:
        if not self._entries:
            return ''
        lines: List[str] = []
        for entry in self._entries[-5:]:
            question = str(entry.get('question') or '').strip()
            answer = str(entry.get('answer') or '').strip()
            intents = ', '.join(entry.get('intents') or [])
            line = f"Q: {question}"
            if intents:
                line += f" | intents: {intents}"
            if answer:
                line += f" | A: {answer[:160]}"
            lines.append(line)
        return '\n'.join(lines)[-max_chars:]


__all__ = ['QueryMemory']