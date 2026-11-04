import pytest
from sqlalchemy import text

from alembic_utils_extended.exceptions import SQLParseFailure
from alembic_utils_extended.pg_function import PGFunction
from alembic_utils_extended.pg_procedure import PGProcedure
from alembic_utils_extended.replaceable_entity import register_entities
from alembic_utils_extended.testbase import (
    TEST_VERSIONS_ROOT,
    run_alembic_command,
)

ADD_TO_LEDGER = PGProcedure(
    schema="public",
    signature="add_to_ledger(account text, amount numeric default 0)",
    definition="""
        language plpgsql
        as
        $$
        declare
            total numeric;
        begin
            total := amount * 2;
            insert into ledger(account, amount) values (account, total);
        end;
        $$;
        """,
)


def read_migration(name: str) -> str:
    with (TEST_VERSIONS_ROOT / name).open() as migration_file:
        return migration_file.read()


def create_ledger_table(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("create table public.ledger (account text, amount numeric)"))


def test_trailing_whitespace_stripped() -> None:
    proc = PGProcedure(schema="public", signature="doThing (a int)", definition="language sql as $$ select 1 $$")
    statements = [
        str(next(iter(proc.to_sql_statement_create()))),
        str(next(iter(proc.to_sql_statement_create_or_replace()))),
        str(next(iter(proc.to_sql_statement_drop()))),
    ]
    for statement in statements:
        assert '"doThing"' in statement
        assert '"doThing "' not in statement


def test_drop_statement_strips_defaults() -> None:
    proc = PGProcedure(
        schema="public",
        signature="p(IN a integer, INOUT b text DEFAULT 'x, y'::text, c numeric(10,2) = 1.5, default_name int)",
        definition="language sql as $$ select 1 $$",
    )
    drop = str(next(iter(proc.to_sql_statement_drop(cascade=True))))
    assert drop.strip() == 'DROP PROCEDURE "public"."p"(IN a integer, INOUT b text, c numeric(10,2), default_name int) cascade'


@pytest.mark.parametrize(
    "sql,schema,signature,definition_start",
    [
        (
            "create procedure public.do_it(a int) language sql as $$ select 1 $$;",
            "public",
            "do_it(a int)",
            "language sql",
        ),
        (
            'CREATE OR REPLACE PROCEDURE "DEV"."doIt"(IN a integer DEFAULT 1)\n LANGUAGE plpgsql\nAS $procedure$ begin null; end; $procedure$',
            "DEV",
            "doIt(IN a integer DEFAULT 1)",
            "LANGUAGE plpgsql",
        ),
        (
            "create procedure public.no_args() begin atomic select 1; end",
            "public",
            "no_args()",
            "begin atomic",
        ),
        (
            "create procedure public.nested(a numeric(10, 2), b text default ')') language sql as $$ select 1 $$",
            "public",
            "nested(a numeric(10, 2), b text default ')')",
            "language sql",
        ),
    ],
)
def test_from_sql(sql: str, schema: str, signature: str, definition_start: str) -> None:
    proc = PGProcedure.from_sql(sql)
    assert proc.schema == schema
    assert proc.signature == signature
    assert proc.definition.startswith(definition_start)


@pytest.mark.parametrize(
    "sql",
    [
        "create function public.f() returns int language sql as $$ select 1 $$",
        "create procedure public.missing_body()",
        "create procedure no_schema() language sql as $$ select 1 $$",
    ],
)
def test_from_sql_failure(sql: str) -> None:
    with pytest.raises(SQLParseFailure):
        PGProcedure.from_sql(sql)


def test_create_revision(engine) -> None:
    create_ledger_table(engine)
    register_entities([ADD_TO_LEDGER], entity_types=[PGProcedure])

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={"autogenerate": True, "rev_id": "1", "message": "create"},
    )

    migration_contents = read_migration("1_create.py")
    assert "op.create_entity" in migration_contents
    assert "op.drop_entity" in migration_contents
    assert "op.replace_entity" not in migration_contents
    assert "from alembic_utils_extended.pg_procedure import PGProcedure" in migration_contents

    run_alembic_command(engine=engine, command="upgrade", command_kwargs={"revision": "head"})

    # The migrated procedure is callable and the plpgsql ":=" assignment survived escaping
    with engine.begin() as connection:
        connection.execute(text("call public.add_to_ledger('acme', 21)"))
        assert connection.execute(text("select amount from public.ledger")).scalar() == 42

    run_alembic_command(engine=engine, command="downgrade", command_kwargs={"revision": "base"})

    with engine.begin() as connection:
        remaining = connection.execute(text("select count(*) from pg_proc where proname = 'add_to_ledger'")).scalar()
    assert remaining == 0


def test_update_revision(engine, execute_all) -> None:
    create_ledger_table(engine)
    with engine.begin() as connection:
        execute_all(connection, ADD_TO_LEDGER.to_sql_statement_create())

    updated = PGProcedure(
        ADD_TO_LEDGER.schema,
        ADD_TO_LEDGER.signature,
        """language sql
        as $$ insert into ledger(account, amount) values (account, amount * 3) $$""",
    )
    register_entities([updated], entity_types=[PGProcedure])

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={"autogenerate": True, "rev_id": "2", "message": "replace"},
    )

    migration_contents = read_migration("2_replace.py")
    assert "op.replace_entity" in migration_contents
    assert "op.create_entity" not in migration_contents
    assert "op.drop_entity" not in migration_contents

    run_alembic_command(engine=engine, command="upgrade", command_kwargs={"revision": "head"})
    with engine.begin() as connection:
        connection.execute(text("call public.add_to_ledger('acme', 2)"))
        assert connection.execute(text("select amount from public.ledger")).scalar() == 6

    run_alembic_command(engine=engine, command="downgrade", command_kwargs={"revision": "base"})
    with engine.begin() as connection:
        definition = connection.execute(text("select pg_get_functiondef('public.add_to_ledger(text, numeric)'::regprocedure)")).scalar()
    assert "total := amount * 2" in definition


def test_noop_revision(engine, execute_all) -> None:
    create_ledger_table(engine)
    with engine.begin() as connection:
        execute_all(connection, ADD_TO_LEDGER.to_sql_statement_create())

    register_entities([ADD_TO_LEDGER], entity_types=[PGProcedure])

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={"autogenerate": True, "rev_id": "3", "message": "do_nothing"},
    )

    migration_contents = read_migration("3_do_nothing.py")
    assert "op.create_entity" not in migration_contents
    assert "op.drop_entity" not in migration_contents
    assert "op.replace_entity" not in migration_contents
    assert "from alembic_utils_extended" not in migration_contents


def test_drop_revision(engine, execute_all) -> None:
    create_ledger_table(engine)
    with engine.begin() as connection:
        execute_all(connection, ADD_TO_LEDGER.to_sql_statement_create())

    # Register no procedures locally
    register_entities([], schemas=["public"], entity_types=[PGProcedure])

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={"autogenerate": True, "rev_id": "1", "message": "drop"},
    )

    migration_contents = read_migration("1_drop.py")
    assert "op.drop_entity" in migration_contents
    assert "op.create_entity" in migration_contents
    assert migration_contents.index("op.drop_entity") < migration_contents.index("op.create_entity")

    run_alembic_command(engine=engine, command="upgrade", command_kwargs={"revision": "head"})
    run_alembic_command(engine=engine, command="downgrade", command_kwargs={"revision": "base"})


def test_out_parameters_and_overloads(engine) -> None:
    # Overloaded procedures, including OUT parameters (PostgreSQL 14+), are tracked separately
    single = PGProcedure(
        schema="public",
        signature="get_total(IN a integer, OUT total integer)",
        definition="language plpgsql as $$ begin total := a; end; $$",
    )
    double = PGProcedure(
        schema="public",
        signature="get_total(IN a integer, IN b integer, OUT total integer)",
        definition="language plpgsql as $$ begin total := a + b; end; $$",
    )
    register_entities([single, double], entity_types=[PGProcedure])

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={"autogenerate": True, "rev_id": "1", "message": "overloads"},
    )
    migration_contents = read_migration("1_overloads.py")
    assert migration_contents.count("op.create_entity") == 2

    run_alembic_command(engine=engine, command="upgrade", command_kwargs={"revision": "head"})
    with engine.begin() as connection:
        assert connection.execute(text("call public.get_total(1, 2, null)")).scalar() == 3
        assert connection.execute(text("call public.get_total(5, null)")).scalar() == 5

    run_alembic_command(engine=engine, command="downgrade", command_kwargs={"revision": "base"})
    with engine.begin() as connection:
        remaining = connection.execute(text("select count(*) from pg_proc where proname = 'get_total'")).scalar()
    assert remaining == 0


def test_sql_standard_body(engine) -> None:
    # BEGIN ATOMIC bodies (PostgreSQL 14+) are parsed when reflected back from the database
    create_ledger_table(engine)
    atomic = PGProcedure(
        schema="public",
        signature="record_default(account text)",
        definition="begin atomic insert into public.ledger(account, amount) values (account, 1); end",
    )
    register_entities([atomic], entity_types=[PGProcedure])

    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={"autogenerate": True, "rev_id": "1", "message": "atomic"},
    )
    assert "op.create_entity" in read_migration("1_atomic.py")

    run_alembic_command(engine=engine, command="upgrade", command_kwargs={"revision": "head"})

    # Once applied, a second autogenerate is a no-op
    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={"autogenerate": True, "rev_id": "2", "message": "atomic_noop"},
    )
    migration_contents = read_migration("2_atomic_noop.py")
    assert "op.create_entity" not in migration_contents
    assert "op.replace_entity" not in migration_contents
    assert "op.drop_entity" not in migration_contents

    run_alembic_command(engine=engine, command="downgrade", command_kwargs={"revision": "base"})


def test_functions_and_procedures_do_not_mix(engine, execute_all) -> None:
    # A function and a procedure with the same name are independent entities
    func = PGFunction(
        schema="public",
        signature="same_name(a integer)",
        definition="returns integer language sql as $$ select a $$",
    )
    proc = PGProcedure(
        schema="public",
        signature="same_name(a integer, b integer)",
        definition="language sql as $$ select 1 $$",
    )
    with engine.begin() as connection:
        execute_all(connection, func.to_sql_statement_create())
        execute_all(connection, proc.to_sql_statement_create())

    with engine.begin() as connection:
        procedures = PGProcedure.from_database(connection, "public")
        functions = PGFunction.from_database(connection, "public")

    assert [x.signature for x in procedures] == ["same_name(IN a integer, IN b integer)"]
    assert [x.signature for x in functions] == ["same_name(a integer)"]

    # Registering only the procedure must not produce a drop for the function (and vice versa)
    register_entities([proc], schemas=["public"], entity_types=[PGProcedure])
    run_alembic_command(
        engine=engine,
        command="revision",
        command_kwargs={"autogenerate": True, "rev_id": "1", "message": "mixed"},
    )
    migration_contents = read_migration("1_mixed.py")
    assert "op.drop_entity" not in migration_contents
    assert "op.create_entity" not in migration_contents
    assert "op.replace_entity" not in migration_contents
