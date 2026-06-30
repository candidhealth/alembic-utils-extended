import pytest
from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    desc,
    func,
    text,
)

from alembic_utils_extended.pg_expression_index import (
    _get_model_expression_indexes,
    _is_expression_index,
)
from alembic_utils_extended.testbase import (
    TEST_VERSIONS_ROOT,
    run_alembic_command,
)


def test_detect_create_expression_index(engine) -> None:
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    Index("idx_test_table_name_lower", func.lower(table.c.name))

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS idx_test_table_name_lower"))

    output = run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "create_expr_idx",
        },
        target_metadata=metadata,
        compare_expression_indexes=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_create_expr_idx.py"

    with migration_path.open() as migration_file:
        migration_contents = migration_file.read()

    assert "op.create_index" in migration_contents
    assert "idx_test_table_name_lower" in migration_contents

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


def test_detect_drop_expression_index(engine) -> None:
    metadata = MetaData()
    Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("CREATE INDEX idx_test_table_name_lower ON test_table (lower(name))"))

    output = run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "drop_expr_idx",
        },
        target_metadata=metadata,
        compare_expression_indexes=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_drop_expr_idx.py"

    with migration_path.open() as migration_file:
        migration_contents = migration_file.read()

    assert "op.drop_index" in migration_contents
    assert "idx_test_table_name_lower" in migration_contents

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


def test_raises_when_expression_index_exists_in_both(engine) -> None:
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    Index("idx_test_table_name_lower", func.lower(table.c.name))

    with engine.begin() as connection:
        metadata.create_all(connection)

    with pytest.raises(RuntimeError, match=r"test_table\.idx_test_table_name_lower"):
        run_alembic_command(
            engine=engine,
            command="revision",
            command_kwargs={
                "autogenerate": True,
                "rev_id": "1",
                "message": "should_raise",
            },
            target_metadata=metadata,
            compare_expression_indexes=True,
        )


def test_raises_lists_every_shared_index(engine) -> None:
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
        Column("email", String(100)),
    )
    Index("idx_test_table_name_lower", func.lower(table.c.name))
    Index("idx_test_table_email_lower", func.lower(table.c.email))

    with engine.begin() as connection:
        metadata.create_all(connection)

    with pytest.raises(RuntimeError) as exc_info:
        run_alembic_command(
            engine=engine,
            command="revision",
            command_kwargs={
                "autogenerate": True,
                "rev_id": "1",
                "message": "should_raise_multi",
            },
            target_metadata=metadata,
            compare_expression_indexes=True,
        )

    message = str(exc_info.value)
    assert "test_table.idx_test_table_name_lower" in message
    assert "test_table.idx_test_table_email_lower" in message
    assert "rename" in message


def test_ignore_regular_column_indexes(engine) -> None:
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    Index("idx_test_table_name", table.c.name)

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS idx_test_table_name"))

    output = run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "ignore_regular",
        },
        target_metadata=metadata,
        compare_expression_indexes=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_ignore_regular.py"

    with migration_path.open() as migration_file:
        migration_contents = migration_file.read()

    assert "idx_test_table_name" not in migration_contents or "op.create_index" not in migration_contents


def test_disabled_by_default(engine) -> None:
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    Index("idx_test_table_name_lower", func.lower(table.c.name))

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS idx_test_table_name_lower"))

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

    assert "idx_test_table_name_lower" not in migration_contents


def test_is_expression_index() -> None:
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )

    regular_index = Index("idx_regular", table.c.name)
    assert _is_expression_index(regular_index) is False

    expr_index = Index("idx_expr", func.lower(table.c.name))
    assert _is_expression_index(expr_index) is True

    mixed_index = Index("idx_mixed", table.c.id, func.lower(table.c.name))
    assert _is_expression_index(mixed_index) is True


def test_get_model_expression_indexes() -> None:
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    Index("idx_regular", table.c.name)
    Index("idx_expr", func.lower(table.c.name))

    indexes = _get_model_expression_indexes(metadata, None)

    assert len(indexes) == 1
    assert indexes[0]["name"] == "idx_expr"
    assert indexes[0]["table_name"] == "test_table"


def test_dev_schema_compared(engine) -> None:
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
        schema="DEV",
    )
    Index("idx_test_table_name_lower", func.lower(table.c.name))

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text('DROP INDEX IF EXISTS "DEV".idx_test_table_name_lower'))

    output = run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "dev_schema",
        },
        target_metadata=metadata,
        compare_expression_indexes=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_dev_schema.py"

    with migration_path.open() as migration_file:
        migration_contents = migration_file.read()

    assert "op.create_index" in migration_contents
    assert "idx_test_table_name_lower" in migration_contents


def test_detect_partial_expression_index(engine) -> None:
    """Partial expression index (postgresql_where clause). Comparator's
    identity-only diff still detects create/drop by name; verify the emitted
    op preserves the WHERE clause so the rebuilt index matches."""
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    Index(
        "idx_test_table_lower_name_partial",
        func.lower(table.c.name),
        postgresql_where=text("id > 0"),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS idx_test_table_lower_name_partial"))

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "partial_expr",
        },
        target_metadata=metadata,
        compare_expression_indexes=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_partial_expr.py"
    migration_contents = migration_path.read_text()

    assert "op.create_index" in migration_contents
    assert "idx_test_table_lower_name_partial" in migration_contents
    assert "postgresql_where" in migration_contents

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


def test_detect_multi_column_expression_index(engine) -> None:
    """Composite index mixing a plain column with an expression. The
    predicate covers this case (`test_is_expression_index`'s idx_mixed); this
    verifies the end-to-end autogen path emits both elements correctly."""
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    Index("idx_test_table_id_lower_name", table.c.id, func.lower(table.c.name))

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS idx_test_table_id_lower_name"))

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "multi_col_expr",
        },
        target_metadata=metadata,
        compare_expression_indexes=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_multi_col_expr.py"
    migration_contents = migration_path.read_text()

    assert "op.create_index" in migration_contents
    assert "idx_test_table_id_lower_name" in migration_contents
    # Both the column and the lower(name) expression should appear in the op.
    assert "id" in migration_contents
    assert "lower" in migration_contents

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


def test_detect_rename_emits_drop_and_create(engine) -> None:
    """An expression-index rename — same expression, different name — should
    surface as drop(old) + create(new). This is the contract that lets you
    express a content-change by renaming, working around the identity-only
    diff's inability to detect expression changes under a stable name."""
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    Index("idx_test_table_new_name", func.lower(table.c.name))

    with engine.begin() as connection:
        metadata.create_all(connection)

    # DB starts with the OLD-name index; model declares NEW-name on the same expression.
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS idx_test_table_new_name"))
        connection.execute(text("CREATE INDEX idx_test_table_old_name ON test_table (lower(name))"))

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "rename_expr_idx",
        },
        target_metadata=metadata,
        compare_expression_indexes=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_rename_expr_idx.py"
    migration_contents = migration_path.read_text()

    assert "op.drop_index" in migration_contents
    assert "idx_test_table_old_name" in migration_contents
    assert "op.create_index" in migration_contents
    assert "idx_test_table_new_name" in migration_contents

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


def test_detect_desc_expression_renders_without_table_qualifier(engine) -> None:
    """desc(Column) historically rendered as `tablename.col DESC`, which Postgres
    rejects inside CREATE INDEX. Verify the rendered expression strips the table
    qualifier (Alembic's render_ddl_sql_expr supplies include_table=False) and the
    resulting migration applies cleanly."""
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    Index("idx_test_table_id_name_desc", table.c.id, desc(table.c.name))

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS idx_test_table_id_name_desc"))

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "desc_expr",
        },
        target_metadata=metadata,
        compare_expression_indexes=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_desc_expr.py"
    migration_contents = migration_path.read_text()

    assert "op.create_index" in migration_contents
    assert "idx_test_table_id_name_desc" in migration_contents
    # The DESC expression must render as `name DESC`, not `test_table.name DESC`.
    assert "test_table.name" not in migration_contents
    assert "DESC" in migration_contents

    # And the migration must actually apply — PG rejects table-qualified refs in CREATE INDEX.
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


def test_raises_on_func_with_string_arg_matching_column_name(engine) -> None:
    """The `func.X("column_name")` anti-pattern (string treated as bound value, not
    column reference) creates an index on a constant string instead of the column.
    Catch it at autogen time rather than letting the wrong index ship silently.

    Pattern in the wild (insurance_card.py): declared at module level alongside one
    real column reference so the Index attaches to the right table, then a sibling
    string-literal Index gets buried with it."""
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    # The first arg (table.c.id) attaches the Index to the table; the second is the buggy func.
    Index("idx_test_table_name_buggy", table.c.id, func.lower("name"))

    with pytest.raises(ValueError, match=r"anti-pattern"):
        run_alembic_command(
            engine=engine,
            command="revision",
            command_kwargs={
                "autogenerate": True,
                "rev_id": "1",
                "message": "should_raise_anti_pattern",
            },
            target_metadata=metadata,
            compare_expression_indexes=True,
        )


def test_allows_legitimate_string_literal_args(engine) -> None:
    """A string arg that doesn't match a column name is treated as an intentional
    literal — e.g. `func.to_tsvector('english', col)` or `func.replace(col, '-', '')`.
    The anti-pattern check must not false-positive on those."""
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    # 'english' is not a column name → legitimate literal, should NOT raise.
    # Use postgresql_using='btree' to avoid GIN-on-tsvector's IMMUTABLE requirement.
    Index("idx_test_table_lower_replace", func.replace(func.lower(table.c.name), "-", ""))

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS idx_test_table_lower_replace"))

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "legit_literal",
        },
        target_metadata=metadata,
        compare_expression_indexes=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_legit_literal.py"
    migration_contents = migration_path.read_text()

    assert "op.create_index" in migration_contents
    assert "idx_test_table_lower_replace" in migration_contents


def test_detect_postgresql_include_clause_is_preserved(engine) -> None:
    """`postgresql_include=[...]` declares covering columns for index-only scans.
    The comparator must preserve it in the emitted op so the rebuilt index keeps
    the covering optimization."""
    metadata = MetaData()
    table = Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
        Column("payload", String(100)),
    )
    Index(
        "idx_test_table_name_lower_include",
        func.lower(table.c.name),
        postgresql_include=["id", "payload"],
    )

    with engine.begin() as connection:
        metadata.create_all(connection)

    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS idx_test_table_name_lower_include"))

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={
            "autogenerate": True,
            "rev_id": "1",
            "message": "include_clause",
        },
        target_metadata=metadata,
        compare_expression_indexes=True,
    )

    migration_path = TEST_VERSIONS_ROOT / "1_include_clause.py"
    migration_contents = migration_path.read_text()

    assert "op.create_index" in migration_contents
    assert "idx_test_table_name_lower_include" in migration_contents
    assert "postgresql_include" in migration_contents
    # And both INCLUDE columns must round-trip.
    assert "id" in migration_contents
    assert "payload" in migration_contents

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
