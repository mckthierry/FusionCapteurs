from setuptools import setup, find_packages

setup(
    name="fce",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "networkx>=3.1",
        "scikit-learn>=1.3",
        "numpy>=1.24",
        "pyyaml>=6.0",
    ],
)
