"""SwssTableWriter — safe ProducerStateTable write experiments.

All writes require --allow-writes and are restricted to SONIC_AI_LAB_TEST* tables.
"""

from __future__ import annotations

from typing import Any

from sonic_consistency_checker.swss.connector import require_swsscommon
from sonic_consistency_checker.swss.safety import validate_write_allowed


class SwssTableWriter:
    """Produces/Deletes test entries via swsscommon.ProducerStateTable."""

    def produce_test_entry(
        self,
        table: str,
        key: str,
        values: dict[str, str],
        allow_writes: bool,
    ) -> dict[str, Any]:
        """Write a test entry using ProducerStateTable.set."""
        try:
            validate_write_allowed(table, allow_writes)

            swsscommon = require_swsscommon()
            db = swsscommon.DBConnector("APPL_DB", 0)
            producer = swsscommon.ProducerStateTable(db, table)

            fvs = swsscommon.FieldValuePairs(list(values.items()))
            producer.set(key, fvs)

            return {
                "success": True,
                "table": table,
                "key": key,
                "values": values,
                "method": "ProducerStateTable.set",
                "message": "Wrote test entry using ProducerStateTable.",
            }
        except Exception as exc:
            return {
                "success": False,
                "table": table,
                "key": key,
                "values": values,
                "method": "ProducerStateTable.set",
                "error": str(exc),
            }

    def delete_test_entry(
        self,
        table: str,
        key: str,
        allow_writes: bool,
    ) -> dict[str, Any]:
        """Delete a test entry using ProducerStateTable.del."""
        try:
            validate_write_allowed(table, allow_writes)

            swsscommon = require_swsscommon()
            db = swsscommon.DBConnector("APPL_DB", 0)
            producer = swsscommon.ProducerStateTable(db, table)

            producer.delete(key)

            return {
                "success": True,
                "table": table,
                "key": key,
                "method": "ProducerStateTable.delete",
                "message": "Deleted test entry using ProducerStateTable.",
            }
        except Exception as exc:
            return {
                "success": False,
                "table": table,
                "key": key,
                "method": "ProducerStateTable.delete",
                "error": str(exc),
            }
