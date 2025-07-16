from typing import TypeVar

import flupy
from flupy import fluent

import alembic_utils_extended
from alembic_utils_extended.experimental._collect_instances import (
    T,
    collect_instances,
    collect_subclasses,
    walk_modules,
)
from alembic_utils_extended.pg_view import PGView
from alembic_utils_extended.replaceable_entity import ReplaceableEntity


def test_walk_modules() -> None:

    all_modules = [x for x in walk_modules(flupy)]
    assert fluent in all_modules


def test_collect_instances() -> None:

    instances = collect_instances(alembic_utils_extended, TypeVar)
    assert T in instances


def test_collect_subclasses() -> None:
    class ImportedSubclass(ReplaceableEntity):
        ...

    classes = collect_subclasses(alembic_utils_extended, ReplaceableEntity)
    assert PGView in classes
    assert ImportedSubclass in classes
