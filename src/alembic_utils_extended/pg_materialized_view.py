# pylint: disable=unused-argument,invalid-name,line-too-long


from typing import Generator

from alembic.autogenerate.api import AutogenContext
from alembic.autogenerate.render import _add_index as render_add_index
from alembic.operations.ops import CreateIndexOp
from parse import parse
from sqlalchemy import Index
from sqlalchemy import text as sql_text
from sqlalchemy.sql.elements import TextClause

from alembic_utils_extended.exceptions import SQLParseFailure
from alembic_utils_extended.replaceable_entity import ReplaceableEntity
from alembic_utils_extended.statement import (
    coerce_to_unquoted,
    normalize_whitespace,
    strip_terminating_semicolon,
)


class PGMaterializedView(ReplaceableEntity):
    """A PostgreSQL Materialized View compatible with `alembic revision --autogenerate`

    Limitations:
        Materialized views may not have other views or materialized views that depend on them.

    **Parameters:**

    * **schema** - *str*: A SQL schema name
    * **signature** - *str*: A SQL view's call signature
    * **definition** - *str*: The SQL select statement body of the view
    * **with_data** - *bool*: Should create and replace statements populate data
    * **indexes** - *list[Index]*: Specifies SqlAlchemy indexes to be created on MaterializedView.
    """

    type_ = "materialized_view"

    def __init__(self, schema: str, signature: str, definition: str, with_data: bool = True, indexes: list[Index] = None):
        self.schema: str = coerce_to_unquoted(normalize_whitespace(schema))
        self.signature: str = coerce_to_unquoted(normalize_whitespace(signature))
        self.definition: str = strip_terminating_semicolon(definition)
        self.with_data = with_data

        # We must specify name so that index.table.name can access this value.
        self.name = self.signature
        self.indexes = indexes

    @classmethod
    def from_sql(cls, sql: str) -> "PGMaterializedView":
        """Create an instance from a SQL string"""

        # Strip optional semicolon and all whitespace from end of definition
        # because the "with data" clause is optional and the alternative would be to enumerate
        # every possibility in the templates
        sql = strip_terminating_semicolon(sql)

        templates = [
            # Enumerate maybe semicolon endings
            "create{}materialized{}view{:s}{schema}.{signature}{:s}as{:s}{definition}{:s}with{:s}data",
            "create{}materialized{}view{:s}{schema}.{signature}{:s}as{:s}{definition}{}with{:s}{no_data}{:s}data",
            "create{}materialized{}view{:s}{schema}.{signature}{:s}as{:s}{definition}",
        ]

        for template in templates:
            result = parse(template, sql, case_sensitive=False)

            if result is not None:
                with_data = not "no_data" in result.named

                # If the signature includes column e.g. my_view (col1, col2, col3) remove them
                signature = result["signature"].split("(")[0]

                return cls(
                    schema=result["schema"],
                    # strip quote characters
                    signature=signature.replace('"', ""),
                    definition=result["definition"],
                    with_data=with_data,
                )

        raise SQLParseFailure(f'Failed to parse SQL into PGView """{sql}"""')

    def to_sql_statement_create(self) -> Generator[TextClause, None, None]:
        """Generates a SQL "create view" statement"""

        # Remove possible semicolon from definition because we're adding a "WITH DATA" clause
        definition = self.definition.rstrip().rstrip(";")

        yield sql_text(
            f'CREATE MATERIALIZED VIEW {self.literal_schema}."{self.signature}" AS {definition} WITH {"NO" if not self.with_data else ""} DATA;'
        )

    def to_sql_statement_drop(self, cascade=False) -> Generator[TextClause, None, None]:
        """Generates a SQL "drop view" statement"""
        cascade = "cascade" if cascade else ""
        yield sql_text(f'DROP MATERIALIZED VIEW {self.literal_schema}."{self.signature}" {cascade}')

    def to_sql_statement_create_or_replace(self) -> Generator[TextClause, None, None]:
        """Generates a SQL "create or replace view" statement"""
        yield sql_text(f"""DROP MATERIALIZED VIEW IF EXISTS {self.literal_schema}."{self.signature}"; """)
        yield from self.to_sql_statement_create()

    def render_self_for_migration(self, omit_definition=False) -> str:
        """Render a string that is valid python code to reconstruct self in a migration"""
        var_name = self.to_variable_name()
        class_name = self.__class__.__name__
        escaped_definition = self.definition if not omit_definition else "# not required for op"

        return f"""{var_name} = {class_name}(
            schema="{self.schema}",
            signature="{self.signature}",
            definition={repr(escaped_definition)},
            with_data={repr(self.with_data)}
        )\n\n"""

    def render_post_create_entity(self, autogen_context: AutogenContext) -> str:
        index_ops = []
        for index in self.indexes if self.indexes else []:
            index.table = self
            index_op = render_add_index(autogen_context, CreateIndexOp.from_index(index))
            index_ops.append(index_op)

        return "\n" + "\n".join(index_ops) + "\n" if index_ops else ""

    @classmethod
    def from_database(cls, sess, schema):
        """Get a list of all functions defined in the db"""
        sql = sql_text(
            f"""
        select
            schemaname schema_name,
            matviewname view_name,
            definition,
            ispopulated is_populated
        from
            pg_matviews
        where
            schemaname not in ('pg_catalog', 'information_schema')
            and schemaname::text like '{schema}';
        """
        )
        rows = sess.execute(sql).fetchall()
        db_views = [cls(x[0], x[1], x[2], with_data=x[3]) for x in rows]

        for view in db_views:
            assert view is not None

        return db_views
