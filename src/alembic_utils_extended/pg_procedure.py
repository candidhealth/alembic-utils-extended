# pylint: disable=unused-argument,invalid-name,line-too-long
import re
from typing import Generator

from sqlalchemy import text as sql_text
from sqlalchemy.sql.elements import TextClause

from alembic_utils_extended.exceptions import SQLParseFailure
from alembic_utils_extended.replaceable_entity import ReplaceableEntity
from alembic_utils_extended.statement import (
    escape_colon_for_plpgsql,
    escape_colon_for_sql,
    normalize_whitespace,
    strip_terminating_semicolon,
)

# Matches the start of a CREATE [OR REPLACE] PROCEDURE statement and an optionally quoted schema
_CREATE_PROCEDURE = re.compile(
    r"""^\s*create\s+(?:or\s+replace\s+)?procedure\s+(?P<schema>"(?:[^"]|"")+"|[^\s."(]+)\s*\.\s*""",
    re.IGNORECASE,
)

_ARGMODES = ("in", "out", "inout", "variadic")


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split *text* on *sep*, ignoring separators nested in parens, brackets or quotes"""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    current: list[str] = []
    for char in text:
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == sep and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _find_closing_paren(text: str, open_idx: int) -> int:
    """Index of the parenthesis that closes the one at *open_idx*, respecting quotes"""
    depth = 0
    quote: str | None = None
    for idx in range(open_idx, len(text)):
        char = text[idx]
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _strip_default(parameter: str) -> str:
    """Remove a ``DEFAULT <expr>`` or ``= <expr>`` clause from a single parameter declaration"""
    quote: str | None = None
    depth = 0
    lowered = parameter.lower()
    for idx, char in enumerate(parameter):
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif depth == 0:
            if char == "=":
                return parameter[:idx].strip()
            if (
                lowered.startswith("default", idx)
                and idx > 0
                and parameter[idx - 1].isspace()
                and (idx + 7 == len(parameter) or parameter[idx + 7].isspace())
            ):
                return parameter[:idx].strip()
    return parameter.strip()


class PGProcedure(ReplaceableEntity):
    """A PostgreSQL Procedure compatible with `alembic revision --autogenerate`

    Procedures (PostgreSQL 11+) differ from functions in that they are invoked with
    ``CALL``, have no return type, and may commit or roll back transactions.

    **Parameters:**

    * **schema** - *str*: A SQL schema name
    * **signature** - *str*: A SQL procedure's call signature, e.g. ``transfer(src int, dst int, amount numeric)``
    * **definition** - *str*: The remaining procedure body and attributes, e.g. ``language plpgsql as $$ ... $$``
    """

    type_ = "procedure"

    def __init__(self, schema: str, signature: str, definition: str):
        super().__init__(schema, signature, definition)
        # Same escaping rules as PGFunction: plpgsql bodies keep ":=" assignments unescaped
        is_plpgsql: bool = "language plpgsql" in normalize_whitespace(definition).lower().replace("'", "")
        escaping_callable = escape_colon_for_plpgsql if is_plpgsql else escape_colon_for_sql
        self.definition: str = escaping_callable(strip_terminating_semicolon(definition))

    @classmethod
    def from_sql(cls, sql: str) -> "PGProcedure":
        """Create an instance from a SQL string"""
        sql = sql.strip()
        match = _CREATE_PROCEDURE.match(sql)
        if match is not None:
            schema = match.group("schema")
            remainder = sql[match.end() :]
            open_idx = remainder.find("(")
            close_idx = _find_closing_paren(remainder, open_idx) if open_idx > 0 else -1
            if close_idx > 0:
                name = remainder[:open_idx].strip()
                # remove possible quotes from the procedure name
                if name.startswith('"') and name.endswith('"'):
                    name = name[1:-1].replace('""', '"')
                signature = name + remainder[open_idx : close_idx + 1]
                definition = remainder[close_idx + 1 :].strip()
                if name and definition:
                    return cls(schema=schema, signature=signature, definition=definition)
        raise SQLParseFailure(f'Failed to parse SQL into PGProcedure """{sql}"""')

    @property
    def literal_signature(self) -> str:
        """Adds quoting around the procedure's name when emitting SQL statements

        e.g.
        'doThing(a int)' -> '"doThing"(a int)'
        """
        name, remainder = self.signature.split("(", 1)
        return '"' + name.strip() + '"(' + remainder

    @property
    def drop_parameters(self) -> str:
        """The argument list used to identify the procedure in a DROP statement (defaults removed)"""
        _, remainder = self.signature.split("(", 1)
        parameters_str = remainder[: remainder.rfind(")")]
        if not parameters_str.strip():
            return ""
        parameters = [_strip_default(x) for x in _split_top_level(parameters_str)]
        return ", ".join(x for x in parameters if x)

    def to_sql_statement_create(self) -> Generator[TextClause, None, None]:
        """Generates a SQL "create procedure" statement for PGProcedure"""
        yield sql_text(f"CREATE PROCEDURE {self.literal_schema}.{self.literal_signature} {self.definition}")

    def to_sql_statement_drop(self, cascade=False) -> Generator[TextClause, None, None]:
        """Generates a SQL "drop procedure" statement for PGProcedure"""
        cascade_str = "cascade" if cascade else ""
        name = self.signature.split("(", 1)[0].strip()
        yield sql_text(f'DROP PROCEDURE {self.literal_schema}."{name}"({self.drop_parameters}) {cascade_str}')

    def to_sql_statement_create_or_replace(self) -> Generator[TextClause, None, None]:
        """Generates a SQL "create or replace procedure" statement for PGProcedure"""
        yield sql_text(f"CREATE OR REPLACE PROCEDURE {self.literal_schema}.{self.literal_signature} {self.definition}")

    @classmethod
    def from_database(cls, sess, schema="%"):
        """Get a list of all procedures defined in the db"""

        # Procedures were introduced in postgres 11
        pg_version = int(sess.execute(sql_text("show server_version_num")).fetchone()[0])
        if pg_version < 110000:
            return []

        sql = sql_text("""
        with extension_procedures as (
            select
                objid as extension_procedure_oid
            from
                pg_depend
            where
                -- depends on an extension
                deptype='e'
                -- is a proc/function
                and classid = 'pg_proc'::regclass
        )

        select
            n.nspname as procedure_schema,
            p.proname as procedure_name,
            pg_get_functiondef(p.oid) as create_statement
        from
            pg_proc p
            left join pg_namespace n on p.pronamespace = n.oid
            left join extension_procedures ep on p.oid = ep.extension_procedure_oid
        where
            n.nspname not in ('pg_catalog', 'information_schema')
            and p.prokind = 'p'
            -- Filter out procedures from extensions
            and ep.extension_procedure_oid is null
            and n.nspname like :schema
        """)

        rows = sess.execute(sql, {"schema": schema}).fetchall()
        return [cls.from_sql(x[2]) for x in rows]
