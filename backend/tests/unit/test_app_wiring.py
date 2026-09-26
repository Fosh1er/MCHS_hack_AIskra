"""Приложение в «чистом» процессе (как uvicorn) регистрирует все ORM-модели: без этого внешние ключи
между модулями (карточка → занятие, назначение) не разрешаются при первой записи."""

import subprocess
import sys

CODE = """
from aiskra.main import create_app
from aiskra.platform.db import Base
create_app()
tables = set(Base.metadata.tables)
assert {'incident_cards', 'assignments', 'training_sessions', 'users', 'dict_services', 'audit_log'} <= tables, tables
"""


def test_all_models_registered_in_fresh_process() -> None:
    result = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
