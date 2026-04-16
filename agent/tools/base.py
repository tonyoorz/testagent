"""数据分析工具基类"""


class DataAnalysisTool:
    """数据分析工具基类"""

    def __init__(self, name: str, description: str, parameters: dict):
        self.name = name
        self.description = description
        self.parameters = parameters

    def execute(self, data, **kwargs):
        """执行工具逻辑，由子类实现"""
        raise NotImplementedError

    def expects_datasets(self) -> bool:
        return False
