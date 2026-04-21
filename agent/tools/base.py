from typing import Any, Dict


class DataAnalysisTool:
    """Minimal base protocol for packaged analysis tools."""

    def __init__(self, name: str, description: str, parameters: Dict[str, Any]):
        self.name = name
        self.description = description
        self.parameters = parameters

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    def expects_datasets(self) -> bool:
        return False
