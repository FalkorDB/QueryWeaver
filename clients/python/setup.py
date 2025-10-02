from setuptools import setup, find_packages

setup(
    name="queryweaver-client",
    version="0.1.0",
    description="Lightweight Python client for QueryWeaver server",
    packages=find_packages(exclude=("tests",)),
    include_package_data=True,
    install_requires=[
        "requests",
    ],
    extras_require={
        "dev": ["pytest"],
    },
)
