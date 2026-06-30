from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, TypedDict, Union

from alembic.autogenerate import comparators
from alembic.autogenerate.api import AutogenContext
from alembic.operations import ops
from sqlalchemy import Column, Index, text
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import BindParameter, TextClause

logger = logging.getLogger(__name__)


class _ExpressionIndexKw(TypedDict, total=False):
    postgresql_using: str
    postgresql_ops: Dict[str, str]
    postgresql_where: str
    postgresql_include: List[str]


class _ExpressionIndexInfo(TypedDict):
    table_name: str
    name: str
    columns: List[Union[str, TextClause]]
    expressions: List[str]
    unique: bool
    kw: _ExpressionIndexKw


@comparators.dispatch_for("schema")
def compare_expression_indexes(
    autogen_context: AutogenContext,
    upgrade_ops: ops.UpgradeOps,
    _schemas: List[Optional[str]],
) -> None:
    if not autogen_context.opts.get("compare_expression_indexes"):
        return

    inspector: Inspector = autogen_context.inspector
    target_metadata = autogen_context.metadata

    if target_metadata is None:
        return

    observed_schemas: Set[Optional[str]] = {table.schema for table in target_metadata.tables.values()}

    for schema_to_use in observed_schemas:

        model_indexes = _get_model_expression_indexes(target_metadata, schema_to_use, autogen_context)
        db_indexes = _get_database_expression_indexes(inspector, target_metadata, schema_to_use)

        model_index_names = {(idx["table_name"], idx["name"]) for idx in model_indexes}
        db_index_names = {(idx["table_name"], idx["name"]) for idx in db_indexes}

        indexes_to_create = model_index_names - db_index_names
        indexes_to_drop = db_index_names - model_index_names

        shared_indexes = model_index_names & db_index_names
        if shared_indexes:
            formatted = ", ".join(f"{table}.{name}" for table, name in sorted(shared_indexes))
            raise RuntimeError(
                f"Expression index(es) exist in both model and database: {formatted}. "
                f"alembic-utils-extended cannot diff expression-index contents. "
                f"To change an expression index, rename it (which produces a drop + create) "
                f"or write a manual migration."
            )

        for table_name, index_name in indexes_to_create:
            index_info = next(idx for idx in model_indexes if idx["table_name"] == table_name and idx["name"] == index_name)
            logger.info(
                "Detected CreateIndexOp for %s.%s",
                table_name,
                index_name,
            )
            create_op = ops.CreateIndexOp(
                index_name=index_name,
                table_name=table_name,
                columns=index_info["columns"],
                schema=schema_to_use,
                unique=index_info.get("unique", False),
                **index_info.get("kw", {}),
            )
            upgrade_ops.ops.append(create_op)

        for table_name, index_name in indexes_to_drop:
            index_info = next(idx for idx in db_indexes if idx["table_name"] == table_name and idx["name"] == index_name)
            logger.info(
                "Detected DropIndexOp for %s.%s",
                table_name,
                index_name,
            )
            create_op_for_reverse = ops.CreateIndexOp(
                index_name=index_name,
                table_name=table_name,
                columns=index_info["columns"],
                schema=schema_to_use,
                unique=index_info.get("unique", False),
            )
            drop_op = ops.DropIndexOp(
                index_name=index_name,
                table_name=table_name,
                schema=schema_to_use,
                _reverse=create_op_for_reverse,
            )
            upgrade_ops.ops.append(drop_op)


def _is_expression_index(index: Index) -> bool:
    for expr in index.expressions:
        if not isinstance(expr, Column):
            return True
    return False


def _get_model_expression_indexes(metadata, schema: Optional[str], autogen_context: Optional[AutogenContext] = None) -> List[_ExpressionIndexInfo]:
    indexes: List[_ExpressionIndexInfo] = []

    for table in metadata.tables.values():
        if table.schema != schema:
            continue

        for index in table.indexes:
            if not _is_expression_index(index):
                continue

            if index.name is None:
                raise ValueError(
                    f"Unnamed expression index on table '{table.name}'. "
                    f"All expression indexes must have a name for autogenerate support."
                )

            columns = []
            expressions_list = []
            for expr in index.expressions:
                if isinstance(expr, Column):
                    columns.append(expr.name)
                    expressions_list.append(expr.name)
                else:
                    _raise_if_string_arg_matches_column_name(expr, table, index.name)
                    expr_str = _render_index_expression(expr, autogen_context)
                    columns.append(text(expr_str))
                    expressions_list.append(expr_str)

            kw: _ExpressionIndexKw = {}
            if hasattr(index, "dialect_options") and "postgresql" in index.dialect_options:
                pg_opts = index.dialect_options["postgresql"]
                if pg_opts.get("using"):
                    kw["postgresql_using"] = pg_opts["using"]
                if pg_opts.get("ops"):
                    kw["postgresql_ops"] = pg_opts["ops"]
                if pg_opts.get("where") is not None:
                    kw["postgresql_where"] = _render_index_expression(pg_opts["where"], autogen_context)
                if pg_opts.get("include"):
                    kw["postgresql_include"] = list(pg_opts["include"])

            indexes.append(
                {
                    "table_name": table.name,
                    "name": index.name,
                    "columns": columns,
                    "expressions": expressions_list,
                    "unique": index.unique,
                    "kw": kw,
                }
            )

    return indexes


def _raise_if_string_arg_matches_column_name(expr, table, index_name: str) -> None:
    """Catch the `func.X("column_name_str")` anti-pattern.

    SQLAlchemy treats bare strings inside `func.X(...)` as bound-parameter LITERAL
    VALUES, not column references — `func.lower("payer_name")` compiles to
    `lower(:literal_1)` with the value `'payer_name'`, NOT to `lower(payer_name)`.
    The resulting index is on the constant string and useless. Catch it at autogen
    time by walking the expression tree for BindParameter values whose strings
    match a column name on the index's table — that combination is almost always
    the bug rather than an intentional literal.
    """
    column_names = {col.name for col in table.columns}
    for elem in visitors.iterate(expr):
        if isinstance(elem, BindParameter) and isinstance(elem.value, str) and elem.value in column_names:
            raise ValueError(
                f"Expression index {index_name!r} on table {table.name!r} references a string "
                f"literal {elem.value!r} that matches a column on the same table. This is the "
                f"`func.X({elem.value!r})` anti-pattern — the string is being bound as a parameter "
                f"value, not a column reference, so the index is on the constant string. Use "
                f"`func.X(table.c.{elem.value})` or `func.X(literal_column({elem.value!r}))` instead.",
            )


def _render_index_expression(expr, autogen_context: Optional[AutogenContext]) -> str:
    """Render a SQLAlchemy expression as a SQL string suitable for CREATE INDEX.

    Delegates to Alembic's `render_ddl_sql_expr`, which supplies the right compile
    flags (`literal_binds=True`, `include_table=False`) and the postgres-dialect-aware
    handling of index expression self-grouping. Falls back to a plain `str(expr)` only
    when no autogen_context is supplied (test paths exercising the predicate alone)."""
    if autogen_context is None or not hasattr(expr, "compile"):
        return str(expr)
    return autogen_context.migration_context.impl.render_ddl_sql_expr(expr, is_index=True)


def _get_database_expression_indexes(
    inspector: Inspector,
    metadata,
    schema: Optional[str],
) -> List[_ExpressionIndexInfo]:
    indexes: List[_ExpressionIndexInfo] = []

    for table in metadata.tables.values():
        if table.schema != schema:
            continue

        try:
            db_indexes = inspector.get_indexes(table.name, schema=schema)
        except NotImplementedError:
            logger.warning("Database dialect does not support get_indexes. " "Expression index autogenerate is not available.")
            return []
        except NoSuchTableError:
            continue

        for idx in db_indexes:
            if idx.get("name") is None:
                continue

            expressions = idx.get("expressions")
            if not expressions:
                continue

            column_names = idx.get("column_names", [])
            has_expression = False
            for i, expr in enumerate(expressions):
                if i < len(column_names) and column_names[i] is None:
                    has_expression = True
                    break
                elif expr is not None and (i >= len(column_names) or column_names[i] != expr):
                    has_expression = True
                    break

            if not has_expression:
                continue

            columns = []
            expressions_list = []
            for i, expr in enumerate(expressions):
                if i < len(column_names) and column_names[i] is not None:
                    columns.append(column_names[i])
                    expressions_list.append(column_names[i])
                else:
                    expr_str = str(expr)
                    columns.append(text(expr_str))
                    expressions_list.append(expr_str)

            indexes.append(
                {
                    "table_name": table.name,
                    "name": idx["name"],
                    "columns": columns,
                    "expressions": expressions_list,
                    "unique": idx.get("unique", False),
                    "kw": {},
                }
            )

    return indexes
