"""Shared pytest configuration — adds app/ to sys.path so tests can import app modules."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
