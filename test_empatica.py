import fcntl
import io
import os
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

HAS_PARSER_DEPS = all(find_spec(name) is not None for name in ("boto3", "numpy"))

if HAS_PARSER_DEPS:
    import boto3
    from botocore.response import StreamingBody
    from botocore.stub import Stubber

    from run import load_config, load_parser
    from source.checkers.api.empatica import EmpaticaAPICheckerMixin


BUCKET = "example-empatica"
PREFIX = "v2/ORG/STUDY/SITE/"
DAY = "participant_data/2026-11-05/P0001-DEVICE/"
RAW = DAY + "raw_data/v6/STUDY-SITE-P0001_1793836800.avro"
CSV = DAY + "digital_biomarkers/aggregated_per_minute/STUDY-SITE-P0001_2026-11-05_pulse-rate.csv"
REPO = Path(__file__).resolve().parent


def object_entry(path, etag='"original"', size=3):
    return {"Key": PREFIX + path, "ETag": etag, "Size": size}


@unittest.skipUnless(HAS_PARSER_DEPS, "Install the Empatica parser dependencies from the example TOML.")
class EmpaticaTest(unittest.TestCase):
    def setUp(self):
        contexts = ExitStack()
        self.addCleanup(contexts.close)
        self.root = Path(contexts.enter_context(tempfile.TemporaryDirectory()))
        self.config = load_config(REPO / "examples/empatica_config.toml")
        init = self.config["parser"]["init"]
        init["state_path"] = str(self.root / "state")
        init["source"].update(s3_uri=f"s3://{BUCKET}/{PREFIX}", path=str(self.root / "stage"))
        self.target = self.root / "target"
        self.target.mkdir()
        init["target"]["path"] = str(self.target)
        self.parser = load_parser(self.config["parser"])
        self.statuses = []
        self.parser.end_notifiers.append(self.statuses.append)
        client = boto3.client(
            "s3", region_name="us-east-1",
            aws_access_key_id="test", aws_secret_access_key="test",
        )
        self.stub = contexts.enter_context(Stubber(client))
        contexts.enter_context(patch.object(EmpaticaAPICheckerMixin, "make_s3_client", return_value=client))

    def list_objects(self, contents, continuation=None, next_page=None):
        params = {"Bucket": BUCKET, "Prefix": PREFIX}
        if continuation:
            params["ContinuationToken"] = continuation
        response = {"Contents": contents, "IsTruncated": bool(next_page)}
        if next_page:
            response["NextContinuationToken"] = next_page
        self.stub.add_response("list_objects_v2", response, params)

    def get_object(self, obj, data=b"old"):
        self.stub.add_response(
            "get_object", {"Body": StreamingBody(io.BytesIO(data), len(data))},
            {"Bucket": BUCKET, "Key": obj["Key"], "IfMatch": obj["ETag"]},
        )

    def run_parser(self, status=0):
        self.parser.process()
        self.assertEqual(self.statuses[-1], status)
        self.stub.assert_no_pending_responses()
        self.assertEqual(list((self.root / "stage").iterdir()), [])

    def test_paginated_import_then_no_op(self):
        raw, csv = object_entry(RAW), object_entry(CSV)
        self.list_objects([raw], next_page="second")
        self.get_object(raw, b"AVR")
        self.list_objects([csv, object_entry("metadata/participants.csv")], continuation="second")
        self.get_object(csv, b"CSV")
        self.run_parser()
        self.assertEqual((self.target / RAW).read_bytes(), b"AVR")
        self.assertEqual((self.target / CSV).read_bytes(), b"CSV")
        self.assertEqual(len(self.parser.load_state()["success"]), 2)

        self.list_objects([raw, csv])
        self.run_parser()
        self.assertEqual(len(self.parser.load_state()["success"]), 2)

    def test_same_size_revision_replaces_file_and_missing_file_is_repaired(self):
        old, revised = object_entry(CSV), object_entry(CSV, '"revised"')
        for obj, data in [(old, b"old"), (revised, b"new")]:
            self.list_objects([obj])
            self.get_object(obj, data)
            self.run_parser()
            self.assertEqual((self.target / CSV).read_bytes(), data)

        (self.target / CSV).unlink()
        self.list_objects([revised])
        self.get_object(revised, b"new")
        self.run_parser()
        self.assertEqual((self.target / CSV).read_bytes(), b"new")
        self.assertEqual(self.parser.load_state()["success"][0]["etag"], '"revised"')

    def test_same_size_local_change_is_repaired(self):
        csv = object_entry(CSV)
        self.list_objects([csv])
        self.get_object(csv)
        self.run_parser()
        published = self.target / CSV
        original_mtime = published.stat().st_mtime_ns
        published.write_bytes(b"bad")
        os.utime(published, ns=(original_mtime, original_mtime + 2_000_000_000))

        self.list_objects([csv])
        self.get_object(csv)
        self.run_parser()
        self.assertEqual(published.read_bytes(), b"old")

    def test_changed_during_download_is_retried_while_other_file_succeeds(self):
        raw, csv = object_entry(RAW), object_entry(CSV)
        self.list_objects([raw, csv])
        self.stub.add_client_error(
            "get_object", service_error_code="PreconditionFailed", http_status_code=412,
            expected_params={"Bucket": BUCKET, "Key": raw["Key"], "IfMatch": raw["ETag"]},
        )
        self.get_object(csv)
        self.run_parser()
        self.assertFalse((self.target / RAW).exists())
        self.assertTrue((self.target / CSV).is_file())
        self.assertEqual(len(self.parser.load_state()["failure"]), 1)

        revised = object_entry(RAW, '"updated"')
        self.list_objects([revised, csv])
        self.get_object(revised, b"new")
        self.run_parser()
        self.assertEqual((self.target / RAW).read_bytes(), b"new")
        self.assertEqual(self.parser.load_state()["failure"], [])

    def test_copy_failure_keeps_success_state_and_retries(self):
        old, revised = object_entry(CSV), object_entry(CSV, '"revised"')
        self.list_objects([old])
        self.get_object(old)
        self.run_parser()

        self.list_objects([revised])
        self.get_object(revised, b"new")
        def interrupt_publish(source, destination):
            Path(destination).write_bytes(b"n")
            raise OSError("simulated destination write failure")

        with patch.object(shutil, "copy", side_effect=interrupt_publish):
            self.run_parser()
        self.assertEqual(len(self.parser.load_state()["failure"]), 1)
        self.assertEqual(self.parser.load_state()["success"][0]["etag"], '"original"')

        self.list_objects([revised])
        self.get_object(revised, b"new")
        self.run_parser()
        self.assertEqual((self.target / CSV).read_bytes(), b"new")
        self.assertEqual(self.parser.load_state()["failure"], [])

    def test_skips_out_of_scope_keys_and_traversal(self):
        self.parser.source_location["start_date"] = "2026-11-05"
        self.list_objects([
            object_entry(RAW.replace("2026-11-05", "2026-11-04")),
            object_entry(RAW.replace("2026-11-05", "2026-11-31")),
            object_entry(RAW.replace("raw_data/v6", "raw_data/..")),
            object_entry(RAW.replace("P0001-DEVICE", "P0001")),
            object_entry(CSV.replace("aggregated_per_minute", "unrecognized")),
            object_entry(DAY),
        ])
        self.run_parser()
        self.assertEqual(list(self.target.iterdir()), [])

    def test_short_download_does_not_publish(self):
        raw = object_entry(RAW, size=9)
        self.list_objects([raw])
        self.get_object(raw)
        self.run_parser()
        self.assertFalse((self.target / RAW).exists())
        self.assertEqual(self.parser.load_state()["success"], [])
        self.assertEqual(len(self.parser.load_state()["failure"]), 1)

    def test_concurrent_process_does_not_enter_pipeline(self):
        state_root = Path(self.parser.state_path)
        state_root.mkdir()
        with (state_root / ".empatica.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaisesRegex(RuntimeError, "state lock"):
                self.parser.process()

    def test_listing_failure_reports_failed_run(self):
        self.stub.add_client_error(
            "list_objects_v2", service_error_code="AccessDenied", http_status_code=403,
            expected_params={"Bucket": BUCKET, "Prefix": PREFIX},
        )
        self.run_parser(status=1)
        self.assertEqual(self.parser.load_state()["success"], [])


if __name__ == "__main__":
    unittest.main()
