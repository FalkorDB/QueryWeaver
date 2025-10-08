"""Setup script for the QueryWeaver Python client package."""

from setuptools import setup, find_packages  # pylint: disable=import-error

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="queryweaver-client",
    version="0.1.0",
    author="QueryWeaver Team",
    author_email="support@falkordb.com",
    description="Lightweight Python client for QueryWeaver server",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/FalkorDB/QueryWeaver",
    project_urls={
        "Bug Tracker": "https://github.com/FalkorDB/QueryWeaver/issues",
        "Documentation": "https://github.com/FalkorDB/QueryWeaver/tree/main/clients/python",
        "Source Code": "https://github.com/FalkorDB/QueryWeaver",
    },
    packages=find_packages(exclude=("tests",)),
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Topic :: Database",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Framework :: AsyncIO",
    ],
    python_requires=">=3.8",
    install_requires=[
        "aiohttp>=3.8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pylint>=2.17.0",
        ],
    },
    keywords="queryweaver text2sql database api-client aiohttp async",
)
