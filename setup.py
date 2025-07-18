import os
import re

from setuptools import find_packages, setup


def get_version(package):
    """
    Return package version as listed in `__version__` in `__init__.py`.
    """
    with open(os.path.join("src", package, "__init__.py")) as f:
        return re.search("__version__ = ['\"]([^'\"]+)['\"]", f.read()).group(1)


DEV_REQUIRES = [
    "black",
    "pylint",
    "pre-commit",
    "mypy",
    "psycopg2-binary",
    "pytest",
    "pytest-cov",
    "mkdocs",
]

setup(
    name="alembic-utils-extended",
    version=get_version("alembic-utils-extended"),
    author="Justin Malin",
    author_email="justin@joincandidhealth.com",
    license="MIT",
    description="A sqlalchemy/alembic extension for migrating entities like functions, triggers, views, and materialized views.",
    python_requires=">=3.7",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=[
        "alembic>=1.9",
        "flupy",
        "parse>=1.8.4",
        "sqlalchemy>=1.4",
        "typing_extensions",
    ],
    extras_require={
        "dev": DEV_REQUIRES,
        "nvim": ["neovim", "python-language-server"],
        "docs": ["mkdocs", "pygments", "pymdown-extensions", "mkautodoc"],
    },
    package_data={"": ["py.typed"]},
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: SQL",
    ],
)
