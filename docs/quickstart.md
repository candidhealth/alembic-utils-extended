## Quickstart

### Installation

```shell
$ pip install alembic_utils_extended
```

Add `alembic_utils_extended` to the logger keys in `alembic.ini` and a configuration for it.

```
...
[loggers]
keys=root,sqlalchemy,alembic,alembic_utils_extended

[logger_alembic_utils_extended]
level = INFO
handlers =
qualname = alembic_utils_extended
```

### Reference

```python
# migrations/env.py

from alembic_utils_extended.pg_view import PGView
from alembic_utils_extended.replaceable_entity import register_entities

view = PGView(schema="public", signature="view", definition="SELECT 1")
register_entities([view])
```

The next time you autogenerate a revision, Alembic will detect if your entities are new, updated, or removed and
populate the migration script.

```shell
alembic revision --autogenerate -m 'message'
```

For example outputs, check the [examples](examples.md).
