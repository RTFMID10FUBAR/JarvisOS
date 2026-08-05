"""Case Command — Jacob Kerr's authoritative litigation record.

Case Command is the single canonical store for matters, documents, facts,
issues, evidence, deadlines, contradictions, and appeal-preservation state.
Fleet agents may propose changes; only an approved proposal enters the record.

Design invariants enforced throughout this package:

* One document, one physical location, one canonical ID, one matter assignment,
  and any number of cross-matter *links* — never copies.
* Nothing in the canonical record is deleted. Records change status.
* No item is marked verified without a source document and a locator.
* Presence in a folder is never proof that a document was filed.
* Anything destructive requires explicit human approval and is off by default.
"""

__version__ = "1.0.0"

APP_NAME = "Case Command"

from .config import Config, load_config  # noqa: E402,F401

__all__ = ["Config", "load_config", "APP_NAME", "__version__"]
