# Alembic Utils

<p>
    <a href="https://github.com/candidhealth/alembic-utils-extended/actions">
        <img src="https://github.com/candidhealth/alembic-utils-extended/workflows/Tests/badge.svg" alt="Test Status" height="18">
    </a>
    <a href="https://github.com/candidhealth/alembic-utils-extended/actions">
        <img src="https://github.com/candidhealth/alembic-utils-extended/workflows/pre-commit%20hooks/badge.svg" alt="Pre-commit Status" height="18">
    </a>
</p>
<p>
    <a href="https://github.com/candidhealth/alembic-utils-extended/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/markdown-subtemplate.svg" alt="License" height="18"></a>
    <a href="https://badge.fury.io/py/alembic-utils-extended"><img src="https://badge.fury.io/py/alembic-utils-extended.svg" alt="PyPI version" height="18"></a>
    <a href="https://github.com/psf/black">
        <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Codestyle Black" height="18">
    </a>
    <a href="https://pypi.org/project/alembic-utils-extended/"><img src="https://img.shields.io/pypi/dm/alembic-utils-extended.svg" alt="Download count" height="18"></a>
</p>
<p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python version" height="18"></a>
    <a href=""><img src="https://img.shields.io/badge/postgresql-11+-blue.svg" alt="PostgreSQL version" height="18"></a>
</p>

**Autogenerate Support for PostgreSQL Functions, Views, Materialized View, Triggers, and Policies**

This is a fork of the much more popular [alembic_utils](https://github.com/candidhealth/alembic-utils-extended) package to extend the
capabilities of [Alembic](https://alembic.sqlalchemy.org/en/latest/), which adds support for autogenerating a larger
number of [PostgreSQL](https://www.postgresql.org/) entity types,
including [functions](https://www.postgresql.org/docs/current/sql-createfunction.html), [views](https://www.postgresql.org/docs/current/sql-createview.html), [materialized views](https://www.postgresql.org/docs/current/sql-creatematerializedview.html), [triggers](https://www.postgresql.org/docs/current/sql-createtrigger.html),
and [policies](https://www.postgresql.org/docs/current/sql-createpolicy.html).

## Quickstart

Visit the [quickstart guide](docs/quickstart.md) for usage instructions.

```python
# migrations/env.py

from alembic_utils_extended.pg_view import PGView
from alembic_utils_extended.replaceable_entity import register_entities

view = PGView(
    schema="public",
    signature="view",
    definition="SELECT 1")
register_entities([view])
```

The next time you autogenerate a revision, Alembic will detect if your entities are new, updated, or removed and
populate the migration script.

```shell
alembic revision --autogenerate -m 'message'
```

## Contributing

If you have any issues with contributing, please reach out to justin@joincandidhealth.com so that we can work out any
issues you are having! This is mostly just forked directly
from [alembic_utils](https://github.com/candidhealth/alembic-utils-extended), so it's possible something is misconfigured.

### Testing

```
# install pip dependencies
pip install wheel && pip install -e ".[dev]"

# run the tests
pytest src/test
```

### Linting / Pre-Commit Checks

```
pip install pre-commit
pre-commit install

# manually run
pre-commit run --all
```
