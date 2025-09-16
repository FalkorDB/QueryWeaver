"""Setup script for QueryWeaver library."""

from setuptools import setup, find_packages
import os

def read_requirements():
    """Read requirements from Pipfile."""
    requirements = []
    # Core dependencies needed for the library functionality
    requirements = [
        "falkordb>=1.2.0",
        "litellm>=1.76.3", 
        "psycopg2-binary>=2.9.9",
        "pymysql>=1.1.0",
        "jsonschema>=4.25.0",
        "tqdm>=4.67.1",
        "graphiti-core @ git+https://github.com/FalkorDB/graphiti.git@staging"
    ]
    return requirements

def read_dev_requirements():
    """Read development requirements."""
    return [
        "pytest>=8.4.2",
        "pylint>=3.3.4",
        "playwright>=1.55.0",
        "pytest-playwright>=0.7.1",
        "pytest-asyncio>=1.1.0"
    ]

# Read the README file for long description
def read_readme():
    """Read README file."""
    readme_path = os.path.join(os.path.dirname(__file__), "README.md")
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            return f.read()
    return "QueryWeaver Python Library - Text2SQL with graph-powered schema understanding"

setup(
    name="queryweaver",
    version="1.0.0",
    description="Python library for Text2SQL using graph-powered schema understanding",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="FalkorDB",
    author_email="team@falkordb.com",
    url="https://github.com/FalkorDB/QueryWeaver",
    package_dir={"": "src"},
    packages=find_packages(where="src", include=["queryweaver", "queryweaver.*"]),
    py_modules=["api.config"],
    python_requires=">=3.11",
    install_requires=read_requirements(),
    extras_require={
        "dev": read_dev_requirements(),
        "fastapi": [
            "fastapi>=0.116.1",
            "uvicorn>=0.35.0",
            "authlib>=1.6.2",
            "itsdangerous>=2.2.0",
            "python-multipart>=0.0.10",
            "jinja2>=3.1.4",
            "fastapi-mcp>=0.4.0"
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Database",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords="sql text2sql natural-language database query ai llm graph",
    project_urls={
        "Documentation": "https://falkordb.github.io/QueryWeaver/",
        "Source": "https://github.com/FalkorDB/QueryWeaver",
        "Tracker": "https://github.com/FalkorDB/QueryWeaver/issues",
    },
    include_package_data=True,
    zip_safe=False,
)