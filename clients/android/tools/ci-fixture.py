#!/usr/bin/env python3
"""Build a fixture record for CI, so the conformance run has a real server.

Kept as a file rather than a heredoc inside the workflow: a shell heredoc
nested in a YAML block scalar is two layers of whitespace significance, and
getting it subtly wrong fails in a way that looks like a test failure.
"""
import sys
from pathlib import Path

from case_command.config import ensure_layout, load_config
from case_command.db import open_database
from case_command.ingest import scan_all
from case_command.tests.fixtures import build_fixture_tree

root = Path(sys.argv[1])
build_fixture_tree(root)
config = load_config(data_root=str(root))
ensure_layout(config)
conn = open_database(config)
results = scan_all(config, conn)
ingested = sum(1 for r in results if r.status == "ingested")
print(f"fixture ready at {root}: {ingested} document(s) ingested")
