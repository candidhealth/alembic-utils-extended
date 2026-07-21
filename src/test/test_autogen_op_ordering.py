"""Autogenerate operation ordering across ReplaceableEntity / fork-managed
indexes and stock table changes.

Root cause these guard against: on Alembic >= 1.18 the schema-level comparators
run through a ``PriorityDispatcher``. ``AutogenContext`` branches the *global*
registry (where this library registers its ``@comparators.dispatch_for("schema")``
functions) BEFORE the built-in table comparator is merged in, so at the default
MEDIUM priority the fork's comparators run *before* the built-in table diff and
their ops get appended to ``upgrade_ops.ops`` ahead of ``CreateTableOp``. The
result is a migration that tries to create a trigger/function/index before the
table it depends on.

These tests drive Alembic's real ``produce_migrations`` autogen path (the same
one ``alembic revision --autogenerate`` uses) and assert dependency-correct
ordering in both directions. They intentionally do NOT go through the shared
``env.py``/``run_alembic_command`` harness, whose ``include_object`` filter
suppresses stock table autogen (which is why the bug never surfaced in the
existing suite).
"""
from alembic.autogenerate import produce_migrations
from alembic.migration import MigrationContext
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from alembic_utils_extended.pg_function import PGFunction
from alembic_utils_extended.pg_trigger import PGTrigger
from alembic_utils_extended.replaceable_entity import (
    register_entities,
    registry,
)
from alembic_utils_extended.testbase import (
    TEST_VERSIONS_ROOT,
    run_alembic_command,
)


def _op_types(op_list) -> list[str]:
    return [type(op).__name__ for op in op_list]


def _autogen_op_types(engine, metadata: MetaData, opts: dict[str, object]) -> tuple[list[str], list[str]]:
    """Run autogenerate and return (upgrade_op_types, downgrade_op_types)."""
    with engine.connect() as conn:
        context = MigrationContext.configure(
            connection=conn,
            opts={"target_metadata": metadata, "include_schemas": False, "compare_type": False, **opts},
        )
        migrations = produce_migrations(context, metadata)
        migrations.upgrade_ops.reverse_into(migrations.downgrade_ops)
        return _op_types(migrations.upgrade_ops.ops), _op_types(migrations.downgrade_ops.ops)


def test_new_table_created_before_dependent_entities(engine) -> None:
    """A function + trigger on a brand-new (metadata-only) table must be emitted
    AFTER ``CreateTableOp`` on upgrade, and dropped BEFORE the table on downgrade."""
    registry.clear()
    metadata = MetaData()
    Table("widget", metadata, Column("id", Integer, primary_key=True))
    function = PGFunction(
        schema="public",
        signature="widget_guard()",
        definition="returns trigger as $$ begin return new; end; $$ language plpgsql",
    )
    trigger = PGTrigger(
        schema="public",
        signature="widget_immutable",
        on_entity="public.widget",
        definition="BEFORE INSERT ON public.widget FOR EACH ROW EXECUTE PROCEDURE public.widget_guard()",
    )
    register_entities([function, trigger], entity_types=[PGFunction, PGTrigger])

    upgrade, downgrade = _autogen_op_types(engine, metadata, {})

    assert "CreateTableOp" in upgrade and "CreateOp" in upgrade, upgrade
    # Table created before the entities that depend on it.
    assert upgrade.index("CreateTableOp") < upgrade.index("CreateOp"), upgrade
    # And on downgrade, entities dropped before the table.
    assert downgrade.index("DropOp") < downgrade.index("DropTableOp"), downgrade


def test_new_table_created_before_dependent_index(engine) -> None:
    """A fork-managed index (compare_indexes=True) on a brand-new table must be
    emitted AFTER ``CreateTableOp`` on upgrade and dropped BEFORE it on downgrade."""
    registry.clear()
    metadata = MetaData()
    table = Table(
        "gadget",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100)),
    )
    Index("ix_gadget_name", table.c.name)

    upgrade, downgrade = _autogen_op_types(engine, metadata, {"compare_indexes": True})

    assert "CreateTableOp" in upgrade and "CreateIndexOp" in upgrade, upgrade
    assert upgrade.index("CreateTableOp") < upgrade.index("CreateIndexOp"), upgrade
    assert downgrade.index("DropIndexOp") < downgrade.index("DropTableOp"), downgrade


# --- Immutability function/trigger builders (matching db_core.immutability). ---
def _immutability_function(table_name: str) -> PGFunction:
    return PGFunction(
        schema="public",
        signature=f"prevent_{table_name}_update()",
        definition=f"""RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '{table_name} records are immutable';
END;
$$ LANGUAGE plpgsql;""",
    )


def _immutability_update_trigger(table_name: str, immutable_column: str) -> PGTrigger:
    # ``BEFORE UPDATE OF <col>`` is validated at CREATE TRIGGER time — the column
    # must already exist, which is exactly the ordering dependency under test.
    return PGTrigger(
        schema="public",
        signature=f"trig__prevent_{table_name}_update",
        on_entity=f"public.{table_name}",
        is_constraint=False,
        definition=f'BEFORE UPDATE OF "{immutable_column}" ON "{table_name}" '
        f"FOR EACH ROW EXECUTE FUNCTION prevent_{table_name}_update();",
    )


def test_add_column_before_trigger_referencing_it_applies_end_to_end(engine) -> None:
    """PR #30022 shape, end-to-end: an existing table gains a net-new column and an
    ImmutableMixin UPDATE trigger whose ``BEFORE UPDATE OF <col>`` references that
    new column. The generated migration must ``ADD COLUMN`` before ``CREATE
    TRIGGER`` — otherwise ``alembic upgrade`` fails with 'column does not exist'.
    This drives the real revision -> upgrade -> downgrade path (compare_tables
    opts stock table autogen back in)."""
    registry.clear()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE expected_payment (id uuid PRIMARY KEY, updated_at timestamptz)"))

    metadata = MetaData()
    Table(
        "expected_payment",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("updated_at", DateTime(timezone=True)),
        Column("account_id", UUID(as_uuid=True)),  # net-new column the trigger references
    )
    register_entities(
        [_immutability_function("expected_payment"), _immutability_update_trigger("expected_payment", "account_id")],
        entity_types=[PGFunction, PGTrigger],
    )

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={"autogenerate": True, "rev_id": "1", "message": "immutable_expected_payment"},
        target_metadata=metadata,
        compare_tables=True,
    )

    migration_contents = (TEST_VERSIONS_ROOT / "1_immutable_expected_payment.py").read_text()
    assert "op.add_column" in migration_contents
    assert "op.create_entity" in migration_contents
    # ADD COLUMN must be rendered before the trigger/function that depend on it.
    assert migration_contents.index("op.add_column") < migration_contents.index("op.create_entity"), migration_contents

    # The real proof: it must apply cleanly in both directions. Pre-fix this
    # raised 'column "account_id" ... does not exist' during CREATE TRIGGER.
    run_alembic_command(engine=engine, command="upgrade", command_kwargs={"revision": "head"}, target_metadata=metadata)
    run_alembic_command(engine=engine, command="downgrade", command_kwargs={"revision": "base"}, target_metadata=metadata)
