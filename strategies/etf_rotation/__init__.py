"""rQuant.strategies.etf_rotation — 跨境/红利低波 ETF 策略包"""

from . import cross_border_dca, dividend_lowvol_rotation  # noqa: F401
from .universe import CROSS_BORDER_ETFS, DIVIDEND_LOWVOL_ETFS, all_rotation_etfs

__all__ = [
    "CROSS_BORDER_ETFS",
    "DIVIDEND_LOWVOL_ETFS",
    "all_rotation_etfs",
    "cross_border_dca",
    "dividend_lowvol_rotation",
]
