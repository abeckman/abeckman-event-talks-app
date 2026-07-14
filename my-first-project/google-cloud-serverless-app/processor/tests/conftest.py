"""
conftest.py — Shared pytest fixtures and configuration.

Ensures the processor/ directory is on sys.path so that test files can
import main, processor, and bigquery_client without installing the package.
"""

import sys
import os

# Add the processor directory to the path when running tests from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
