# Alembic Utils Extended

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
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python version" height="18"></a>
    <a href=""><img src="https://img.shields.io/badge/postgresql-11+-blue.svg" alt="PostgreSQL version" height="18"></a>
</p>

This is a fork of the much more popular [alembic_utils](https://github.com/candidhealth/alembic-utils-extended) package
to extend the capabilities of [Alembic](https://alembic.sqlalchemy.org/en/latest/), which adds support for
autogenerating a larger number of [PostgreSQL](https://www.postgresql.org/) entity types,
including [functions](https://www.postgresql.org/docs/current/sql-createfunction.html), [views](https://www.postgresql.org/docs/current/sql-createview.html), [materialized views](https://www.postgresql.org/docs/current/sql-creatematerializedview.html), [triggers](https://www.postgresql.org/docs/current/sql-createtrigger.html),
and [policies](https://www.postgresql.org/docs/current/sql-createpolicy.html).

Visit the [quickstart guide](quickstart.md) for usage instructions.
