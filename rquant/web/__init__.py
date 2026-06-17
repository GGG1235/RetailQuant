"""rquant.web — Flask Web 层（应用工厂 + 路由 + 视图辅助）"""

from .app_factory import DEFAULT_PORT, create_app, run
from .views import CATEGORY_LABELS

__all__ = ["CATEGORY_LABELS", "DEFAULT_PORT", "create_app", "run"]
