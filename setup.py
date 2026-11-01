from setuptools import setup, find_packages

setup(
    name="sdd_trainer",
    version="0.1.0",
    description="SDD Trainer — AI tutor teaching Spec-Driven Development with GigaChat and LangGraph",
    author="Alex Kul",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        # Core dependencies are pinned in requirements.txt (course convention:
        # install with `pip install -r requirements.txt && pip install -e .`).
    ],
)
