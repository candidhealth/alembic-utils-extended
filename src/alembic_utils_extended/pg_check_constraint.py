from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, Union

from alembic.autogenerate import comparators, renderers
from alembic.autogenerate.api import AutogenContext
from alembic.operations import ops
from sqlalchemy import CheckConstraint, Enum
from sqlalchemy.engine.reflection import Inspector

logger = logging.getLogger(__name__)


def _render_create_check_constraint(
    autogen_context: AutogenContext,
    op: ops.CreateCheckConstraintOp,
) -> str:
    args = [
        repr(op.constraint_name),
        repr(op.table_name),
        repr(str(op.condition)),
    ]
    if op.schema:
        args.append(f"schema={op.schema!r}")
    kw = getattr(op, "kw", {}) or {}
    for key, value in sorted(kw.items()):
        args.append(f"{key}={value!r}")
    return f"op.create_check_constraint({', '.join(args)})"


renderers._registry[(ops.CreateCheckConstraintOp, "default")] = _render_create_check_constraint


@comparators.dispatch_for("schema")
def compare_check_constraints(
    autogen_context: AutogenContext,
    upgrade_ops: ops.UpgradeOps,
    schemas: List[Optional[str]],
) -> None:
    compare_check_constraints_opt: Union[bool, List[str], None] = autogen_context.opts.get("compare_check_constraints")

    if not compare_check_constraints_opt:
        return

    connection = autogen_context.connection
    if connection is None:
        return

    inspector: Inspector = autogen_context.inspector
    target_metadata = autogen_context.metadata

    if target_metadata is None:
        return

    if isinstance(compare_check_constraints_opt, list):
        observed_schemas: Set[str] = set(compare_check_constraints_opt)
    else:
        observed_schemas = {"public"}

    for schema in observed_schemas:
        schema_to_use = schema if schema != "public" else None

        model_constraints = _get_model_check_constraints(target_metadata, schema_to_use)
        db_constraints = _get_database_check_constraints(inspector, target_metadata, schema_to_use)

        model_constraint_names = {(c["table_name"], c["name"]) for c in model_constraints}
        db_constraint_names = {(c["table_name"], c["name"]) for c in db_constraints}

        constraints_to_create = model_constraint_names - db_constraint_names
        constraints_to_drop = db_constraint_names - model_constraint_names

        for table_name, constraint_name in constraints_to_create:
            constraint_info = next(c for c in model_constraints if c["table_name"] == table_name and c["name"] == constraint_name)
            logger.info(
                "Detected CreateCheckConstraintOp for %s.%s",
                table_name,
                constraint_name,
            )
            create_op = ops.CreateCheckConstraintOp(
                constraint_name=constraint_name,
                table_name=table_name,
                condition=constraint_info["sqltext"],
                schema=schema_to_use,
            )
            upgrade_ops.ops.append(create_op)

        for table_name, constraint_name in constraints_to_drop:
            constraint_info = next(c for c in db_constraints if c["table_name"] == table_name and c["name"] == constraint_name)
            logger.info(
                "Detected DropConstraintOp for %s.%s",
                table_name,
                constraint_name,
            )
            create_op_for_reverse = ops.CreateCheckConstraintOp(
                constraint_name=constraint_name,
                table_name=table_name,
                condition=constraint_info["sqltext"],
                schema=schema_to_use,
            )
            drop_op = ops.DropConstraintOp(
                constraint_name=constraint_name,
                table_name=table_name,
                type_="check",
                schema=schema_to_use,
                _reverse=create_op_for_reverse,
            )
            upgrade_ops.ops.append(drop_op)


def _get_model_check_constraints(metadata, schema: Optional[str]) -> List[Dict[str, str]]:
    constraints = []

    for table in metadata.tables.values():
        if table.schema != schema:
            continue

        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                if constraint.name is None:
                    raise ValueError(
                        f"Unnamed check constraint on table '{table.name}'. "
                        f"All check constraints must have a name for autogenerate support. "
                        f"Constraint: {constraint.sqltext}"
                    )

                sqltext = str(constraint.sqltext)
                constraints.append(
                    {
                        "table_name": table.name,
                        "name": constraint.name,
                        "sqltext": sqltext,
                    }
                )

    return constraints


def _get_database_check_constraints(
    inspector: Inspector,
    metadata,
    schema: Optional[str],
) -> List[Dict[str, str]]:
    constraints = []

    for table in metadata.tables.values():
        if table.schema != schema:
            continue

        enum_constraint_names = _get_enum_constraint_names(table)

        try:
            db_constraints = inspector.get_check_constraints(table.name, schema=schema)
        except NotImplementedError:
            logger.warning("Database dialect does not support get_check_constraints. " "Check constraint autogenerate is not available.")
            return []

        for c in db_constraints:
            if c.get("name") is None:
                continue

            if c["name"] in enum_constraint_names:
                continue

            constraints.append(
                {
                    "table_name": table.name,
                    "name": c["name"],
                    "sqltext": c.get("sqltext", ""),
                }
            )

    return constraints


def _get_enum_constraint_names(table) -> Set[str]:
    constraint_names = set()
    for column in table.columns:
        if isinstance(column.type, Enum) and not getattr(column.type, "native_enum", True):
            constraint_names.add(f"{table.name}_{column.name}_check")
    return constraint_names
