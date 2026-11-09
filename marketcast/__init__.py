"""marketcast —— 股票与外汇预测辅助系统。

核心流程：行情数据 -> 技术指标 -> 技术面评分 + 机器学习方向预测
-> 综合结论 -> ATR 风控建议 -> 历史回测验证。
"""

__version__ = "0.1.0"

from .analysis import Analysis, AnalysisConfig, analyze  # noqa: E402
from .data import load_data, normalize_symbol  # noqa: E402

__all__ = ["Analysis", "AnalysisConfig", "analyze", "load_data", "normalize_symbol", "__version__"]
