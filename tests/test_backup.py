import gzip
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

        result = backup.dump_database(
            "icoretech_keychain", "-h localhost -U postgres", str(dest_file)
        )

        self.assertIsNone(result)
        self.assertFalse(dest_file.exists())

    def test_dump_database_keeps_real_dump_output(self):
        self.write_executable(
            "pg_dump",
            "#!/bin/sh\n"
            "printf '%s\n' '-- fake dump' 'CREATE TABLE demo (id integer);'\n",
        )

        dest_file = Path(self.tempdir.name) / "success.sql.gz"

        result = backup.dump_database(
            "icoretech_keychain", "-h localhost -U postgres", str(dest_file)
        )

        self.assertEqual(str(dest_file), result)
        with gzip.open(dest_file, "rt", encoding="utf-8") as handle:
            dump_text = handle.read()
        self.assertIn("CREATE TABLE demo", dump_text)


class MainTest(unittest.TestCase):
    def backup_environment(self):
        return {
            "S3_ACCESS_KEY_ID": "test-access-key",
            "S3_SECRET_ACCESS_KEY": "test-secret-key",
            "S3_BUCKET": "test-bucket",
            "S3_PREFIX": "test-prefix",
            "S3_REGION": "test-region",
            "POSTGRES_HOST": "postgres",
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "test-password",
            "DELETE_OLDER_THAN": "30 days",
        }

    @mock.patch("backup.os.remove")
    @mock.patch("backup.cleanup_old_backups")
    @mock.patch("backup.upload_to_s3", return_value=True)
    @mock.patch("backup.dump_database", side_effect=[None, "/tmp/second.sql.gz"])
    @mock.patch("backup.list_databases", return_value=["first", "second"])
    @mock.patch("backup.get_postgres_version", return_value="pg18")
    def test_main_fails_and_skips_retention_when_a_dump_fails(
        self,
        get_postgres_version,
        list_databases,
        dump_database,
        upload_to_s3,
        cleanup_old_backups,
        remove_file,
    ):
        with mock.patch.dict(os.environ, self.backup_environment(), clear=True):
            with self.assertRaises(SystemExit) as raised:
                backup.main()

        self.assertEqual(1, raised.exception.code)
        self.assertEqual(2, dump_database.call_count)
        upload_to_s3.assert_called_once()
        cleanup_old_backups.assert_not_called()
        remove_file.assert_called_once_with("/tmp/second.sql.gz")
        self.assertTrue(get_postgres_version.called)
        self.assertTrue(list_databases.called)

    @mock.patch("backup.os.remove")
    @mock.patch("backup.cleanup_old_backups")
    @mock.patch("backup.upload_to_s3", return_value=False)
    @mock.patch("backup.dump_database", return_value="/tmp/failed-upload.sql.gz")
    @mock.patch("backup.list_databases", return_value=["only_database"])
    @mock.patch("backup.get_postgres_version", return_value="pg18")
    def test_main_fails_and_skips_retention_when_an_upload_fails(
        self,
        get_postgres_version,
        list_databases,
        dump_database,
        upload_to_s3,
        cleanup_old_backups,
        remove_file,
    ):
        with mock.patch.dict(os.environ, self.backup_environment(), clear=True):
            with self.assertRaises(SystemExit) as raised:
                backup.main()

        self.assertEqual(1, raised.exception.code)
        dump_database.assert_called_once()
        upload_to_s3.assert_called_once()
        cleanup_old_backups.assert_not_called()
        remove_file.assert_called_once_with("/tmp/failed-upload.sql.gz")
        self.assertTrue(get_postgres_version.called)
        self.assertTrue(list_databases.called)

    @mock.patch("backup.os.remove")
    @mock.patch("backup.os.path.exists", return_value=True)
    @mock.patch("backup.cleanup_old_backups")
    @mock.patch("backup.upload_to_s3")
    @mock.patch("backup.encrypt_dump", return_value=None)
    @mock.patch("backup.dump_database", return_value="/tmp/failed-encryption.sql.gz")
    @mock.patch("backup.list_databases", return_value=["only_database"])
    @mock.patch("backup.get_postgres_version", return_value="pg18")
    def test_main_fails_and_skips_retention_when_encryption_fails(
        self,
        get_postgres_version,
        list_databases,
        dump_database,
        encrypt_dump,
        upload_to_s3,
        cleanup_old_backups,
        path_exists,
        remove_file,
    ):
        environment = self.backup_environment()
        environment["ENCRYPTION_PASSWORD"] = "test-encryption-password"

        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(SystemExit) as raised:
                backup.main()

        self.assertEqual(1, raised.exception.code)
        dump_database.assert_called_once()
        encrypt_dump.assert_called_once()
        upload_to_s3.assert_not_called()
        cleanup_old_backups.assert_not_called()
        path_exists.assert_called_once_with("/tmp/failed-encryption.sql.gz")
        remove_file.assert_called_once_with("/tmp/failed-encryption.sql.gz")
        self.assertTrue(get_postgres_version.called)
        self.assertTrue(list_databases.called)


if __name__ == "__main__":
    unittest.main()
