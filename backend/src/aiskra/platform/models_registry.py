"""Импорт всех ORM-моделей для Alembic autogenerate и create-schema.

Добавляя модуль с таблицами — импортируйте здесь его `infrastructure.models`.
"""

from aiskra.modules.assessment.infrastructure import models as _assessment
from aiskra.modules.audit.infrastructure import models as _audit
from aiskra.modules.dictionaries.infrastructure import models as _dictionaries
from aiskra.modules.identity.infrastructure import models as _identity
from aiskra.modules.incidents.infrastructure import models as _incidents
from aiskra.modules.training.infrastructure import models as _training
from aiskra.platform.db import Base

metadata = Base.metadata

__all__ = ["_assessment", "_audit", "_dictionaries", "_identity", "_incidents", "_training", "metadata"]
