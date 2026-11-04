"""Retention failures must propagate across the command boundary."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import backup


class RetentionFailureTest(unittest.TestCase):
    def test_failed_retention_operations_exit_nonzero(self) -> None:
        scenarios = [
            ("list", "exit 1", "30 days"),
            ("delete", "printf '%s\\n' '2000-01-01 00:00:00 100 sample_2000-01-01T000000Z.sql.gz'", "30 days"),
            ("listing", "printf '%s\\n' 'malformed listing'", "30 days"),
            ("timestamp", "printf '%s\\n' 'bad-date 00:00:00 100 sample_2000-01-01T000000Z.sql.gz'", "30 days"),
            ("period", "printf '%s\\n' '2000-01-01 00:00:00 100 sample_2000-01-01T000000Z.sql.gz'", "forever"),
        ]
        for name, listing, period in scenarios:
            with self.subTest(operation=name), tempfile.TemporaryDirectory() as directory:
                executable = Path(directory) / "aws"
                executable.write_text(
                    '#!/bin/sh\ncase "$1 $2" in\n'
                    f'  "s3 ls") {listing} ;;\n'
                    '  "s3 rm") exit 1 ;;\n'
                    '  *) exit 2 ;;\nesac\n'
                )
                executable.chmod(0o700)
                with mock.patch.dict(os.environ, {"PATH": directory}):
                    with self.assertRaises(SystemExit) as raised:
                        backup.cleanup_old_backups(
                            "sample-bucket", "owned-prefix", period, ["sample"]
                        )
                self.assertEqual(1, raised.exception.code)

    def test_empty_prefix_is_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "aws"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            with mock.patch.dict(os.environ, {"PATH": directory}):
                backup.cleanup_old_backups(
                    "sample-bucket", "owned-prefix", "30 days", ["sample"]
                )
