import gzip
import os
import stat
import tempfile
import unittest
from pathlib import Path

import backup


class DumpDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.bin_dir = Path(self.tempdir.name) / "bin"
        self.bin_dir.mkdir()
        self.original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{self.bin_dir}:{self.original_path}"

    def tearDown(self):
        os.environ["PATH"] = self.original_path
        self.tempdir.cleanup()

    def write_executable(self, name, body):
        script_path = self.bin_dir / name
        script_path.write_text(body)
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)
        return script_path

    def test_dump_database_rejects_empty_gzip_when_pg_dump_fails(self):
        self.write_executable(
            "pg_dump",
            "#!/bin/sh\n"
            "echo 'pg_dump: error: aborting because of server version mismatch' >&2\n"
            "exit 1\n",
        )

        dest_file = Path(self.tempdir.name) / "failed.sql.gz"

        result = backup.dump_database("icoretech_keychain", "-h localhost -U postgres", str(dest_file))

        self.assertIsNone(result)
        self.assertFalse(dest_file.exists())

    def test_dump_database_keeps_real_dump_output(self):
        self.write_executable(
            "pg_dump",
            "#!/bin/sh\n"
            "printf '%s\n' '-- fake dump' 'CREATE TABLE demo (id integer);'\n",
        )

        dest_file = Path(self.tempdir.name) / "success.sql.gz"

        result = backup.dump_database("icoretech_keychain", "-h localhost -U postgres", str(dest_file))

        self.assertEqual(str(dest_file), result)
        with gzip.open(dest_file, "rt", encoding="utf-8") as handle:
            dump_text = handle.read()
        self.assertIn("CREATE TABLE demo", dump_text)


if __name__ == "__main__":
    unittest.main()
