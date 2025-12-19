import pytest
from alembic.operations import ops
from sqlalchemy import CheckConstraint, Column, Integer, MetaData, Table, text

from alembic_utils_extended.pg_check_constraint import (
    _constraint_columns_exist_in_metadata,
    _constraint_columns_exist_on_table,
    _render_create_check_constraint,
)
from alembic_utils_extended.testbase import (
    TEST_VERSIONS_ROOT,
    run_alembic_command,
)


def test_create_check_constraint_revision(engine) -> None:
    metadata = MetaData()
    Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", Integer),
        CheckConstraint("amount >= 0", name="ck_test_table_amount_positive"),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE test_table DROP CONSTRAINT ck_test_table_amount_positive"))

    output = run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "create_check",
        },
        target_metadata=metadata,
        compare_check_constraints=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_create_check.py"

    with migration_path.open() as migration_file:
        migration_contents = migration_file.read()

    assert "op.create_check_constraint" in migration_contents
    assert "ck_test_table_amount_positive" in migration_contents

    run_alembic_command(
        engine=engine,
        command="upgrade",
        command_kwargs={"revision": "head"},
        target_metadata=metadata,
    )
    run_alembic_command(
        engine=engine,
        command="downgrade",
        command_kwargs={"revision": "base"},
        target_metadata=metadata,
    )


def test_drop_check_constraint_revision(engine) -> None:
    metadata = MetaData()
    Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", Integer),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE test_table ADD CONSTRAINT ck_test_table_extra " "CHECK (amount < 1000)"))

    output = run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "drop_check",
        },
        target_metadata=metadata,
        compare_check_constraints=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_drop_check.py"

    with migration_path.open() as migration_file:
        migration_contents = migration_file.read()

    assert "op.drop_constraint" in migration_contents
    assert "ck_test_table_extra" in migration_contents

    run_alembic_command(
        engine=engine,
        command="upgrade",
        command_kwargs={"revision": "head"},
        target_metadata=metadata,
    )
    run_alembic_command(
        engine=engine,
        command="downgrade",
        command_kwargs={"revision": "base"},
        target_metadata=metadata,
    )


def test_disabled_by_default(engine) -> None:
    metadata = MetaData()
    Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", Integer),
        CheckConstraint("amount >= 0", name="ck_test_table_amount_positive"),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE test_table DROP CONSTRAINT ck_test_table_amount_positive"))

    output = run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "disabled",
        },
        target_metadata=metadata,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_disabled.py"

    with migration_path.open() as migration_file:
        migration_contents = migration_file.read()

    assert "op.create_check_constraint" not in migration_contents


def test_unnamed_constraint_raises_error(engine) -> None:
    metadata = MetaData()
    Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", Integer),
        CheckConstraint("amount >= 0"),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)

    with pytest.raises(ValueError, match="Unnamed check constraint on table 'test_table'"):
        run_alembic_command(
            engine=engine,
            command="revision",
            command_kwargs={
                "autogenerate": True,
                "rev_id": "1",
                "message": "unnamed",
            },
            target_metadata=metadata,
            compare_check_constraints=True,
        )


def test_different_schema_not_compared(engine) -> None:
    metadata = MetaData()
    Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", Integer),
        CheckConstraint("amount >= 0", name="ck_test_table_amount_positive"),
        schema="DEV",
    )

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE "DEV".test_table DROP CONSTRAINT ck_test_table_amount_positive'))

    output = run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "diff_schema",
        },
        target_metadata=metadata,
        compare_check_constraints=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_diff_schema.py"

    with migration_path.open() as migration_file:
        migration_contents = migration_file.read()

    assert "op.create_check_constraint" not in migration_contents


def test_dev_schema_compared_when_specified(engine) -> None:
    metadata = MetaData()
    Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("amount", Integer),
        CheckConstraint("amount >= 0", name="ck_test_table_amount_positive"),
        schema="DEV",
    )

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE "DEV".test_table DROP CONSTRAINT ck_test_table_amount_positive'))

    output = run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "dev_schema",
        },
        target_metadata=metadata,
        compare_check_constraints=["DEV"],
    )

    migration_path = TEST_VERSIONS_ROOT / "1_dev_schema.py"

    with migration_path.open() as migration_file:
        migration_contents = migration_file.read()

    assert "op.create_check_constraint" in migration_contents
    assert "ck_test_table_amount_positive" in migration_contents


def test_renderer_includes_schema_and_kwargs() -> None:
    op = ops.CreateCheckConstraintOp(
        constraint_name="ck_test",
        table_name="test_table",
        condition="amount >= 0",
        schema="myschema",
    )
    op.kw = {"postgresql_not_valid": True}

    rendered = _render_create_check_constraint(None, op)

    assert "schema='myschema'" in rendered
    assert "postgresql_not_valid=True" in rendered


def test_constraint_with_missing_columns_skipped() -> None:
    metadata = MetaData()
    parent_table = Table(
        "parent_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_column", Integer),
    )
    child_table = Table(
        "child_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("child_column", Integer),
    )

    constraint_on_parent = CheckConstraint(
        parent_table.c.parent_column > 0,
        name="ck_parent_column_positive",
    )

    assert _constraint_columns_exist_on_table(constraint_on_parent, parent_table) is True
    assert _constraint_columns_exist_on_table(constraint_on_parent, child_table) is False


def test_constraint_columns_exist_in_metadata() -> None:
    metadata = MetaData()
    parent_table = Table(
        "parent_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_column", Integer),
    )
    Table(
        "child_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("child_column", Integer),
    )

    constraint_on_parent = CheckConstraint(
        parent_table.c.parent_column > 0,
        name="ck_parent_column_positive",
    )

    assert _constraint_columns_exist_in_metadata(constraint_on_parent, metadata) is True

    orphan_metadata = MetaData()
    Table(
        "orphan_table",
        orphan_metadata,
        Column("id", Integer, primary_key=True),
        Column("other_column", Integer),
    )

    assert _constraint_columns_exist_in_metadata(constraint_on_parent, orphan_metadata) is False


def test_constraint_referencing_nonexistent_column_raises_error() -> None:
    from alembic_utils_extended.pg_check_constraint import (
        _get_model_check_constraints,
    )

    source_metadata = MetaData()
    source_table = Table(
        "source_table",
        source_metadata,
        Column("id", Integer, primary_key=True),
        Column("source_column", Integer),
    )

    target_metadata = MetaData()
    target_table = Table(
        "target_table",
        target_metadata,
        Column("id", Integer, primary_key=True),
        Column("different_column", Integer),
    )
    target_table.append_constraint(
        CheckConstraint(
            source_table.c.source_column > 0,
            name="ck_nonexistent_column",
        )
    )

    with pytest.raises(ValueError, match="references columns that do not exist in any table"):
        _get_model_check_constraints(target_metadata, None)
