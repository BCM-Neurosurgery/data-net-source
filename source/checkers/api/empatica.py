"""Fetch daily EmbracePlus exports from the Empatica S3 data bucket."""

import fcntl
import json
import logging
import shutil
import stat
import tempfile
import time
from contextlib import closing
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from source.checkers.base import BaseChecker
from source.common import EMPTY_LOG


class EmpaticaAPICheckerMixin(BaseChecker):
    """Stage new or revised raw Avro and minute-level biomarker CSV exports."""

    checker_name = "EmpaticaAPIChecker"

    def process(self):
        """Serialize runs sharing a state directory and isolate their staged files."""
        staging_root = Path(self.source_location["path"]).resolve()
        state_root = Path(self.state_path).resolve()
        target_root = Path(self.target_location["path"]).resolve()
        if any(
            staging_root.is_relative_to(root) or root.is_relative_to(staging_root)
            for root in (state_root, target_root)
        ):
            raise ValueError("Empatica staging must be separate from state and target.")
        if not target_root.is_dir():
            raise FileNotFoundError("Create the Empatica target directory on the intended filesystem first.")
        if not self.target_location.get("allow-overwrite"):
            raise ValueError("Empatica needs target allow-overwrite to refresh revised exports.")
        if self.target_location.get("rebuild_filepath"):
            raise ValueError("Empatica preserves the export paths relative to the S3 prefix.")

        staging_root.mkdir(parents=True, exist_ok=True)
        state_root.mkdir(parents=True, exist_ok=True)
        middle_location = self.middle_location
        with (state_root / ".empatica.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("Another Empatica run holds the state lock.") from error
            with tempfile.TemporaryDirectory(prefix="run-", dir=staging_root) as staging:
                self.middle_location = {"path": staging}
                try:
                    return super().process()
                finally:
                    self.middle_location = middle_location

    def make_s3_client(self):
        # ParserCommon enables root DEBUG logging. Keep SDK request details out of the logs.
        for name in ("boto3", "botocore", "urllib3"):
            logging.getLogger(name).setLevel(logging.WARNING)
        session = boto3.Session(
            profile_name=self.source_location.get("aws_profile"),
            region_name=self.source_location.get("region"),
        )
        return session.client("s3", config=Config(retries={"mode": "standard", "total_max_attempts": 5}))

    @staticmethod
    def export_path(key, prefix, start_date):
        """Return a safe prefix-relative path for a supported daily export."""
        if not key.startswith(prefix):
            return None
        parts = key[len(prefix):].split("/")
        if any(part in ("", ".", "..") or "\\" in part for part in parts):
            return None
        if "participant_data" not in parts:
            return None
        tail = parts[parts.index("participant_data") + 1:]
        if len(tail) != 5:
            return None
        day, device, category, subdivision, filename = tail
        try:
            recording_date = date.fromisoformat(day)
        except ValueError:
            return None
        if recording_date.isoformat() != day or (start_date and recording_date < start_date):
            return None
        if "-" not in device:
            return None
        is_raw = category == "raw_data" and filename.lower().endswith(".avro")
        is_biomarker = (
            category == "digital_biomarkers"
            and subdivision == "aggregated_per_minute"
            and filename.lower().endswith(".csv")
        )
        if is_raw or is_biomarker:
            return Path(*parts)
        return None

    def check(self):
        source = self.source_location
        uri = urlsplit(source["s3_uri"])
        prefix = uri.path.strip("/") + "/"
        if (
            uri.scheme != "s3" or not uri.netloc or not uri.path.strip("/")
            or uri.query or uri.fragment or "participant_data" in prefix.split("/")
        ):
            raise ValueError("Set s3_uri to the scoped Empatica S3 prefix above participant_data.")
        bucket = uri.netloc
        start_date = date.fromisoformat(str(source["start_date"])) if "start_date" in source else None

        self._state = self.load_state()
        self._staged = {}
        saved = {
            (item["s3_bucket"], item["s3_key"]): item for item in self._state["success"]
        }
        staging = Path(self.middle_location["path"])
        target = Path(self.target_location["path"]).resolve()
        tasks, failures = [], []
        with closing(self.make_s3_client()) as client:
            pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
            for page in pages:
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    relative = self.export_path(key, prefix, start_date)
                    if relative is None:
                        continue

                    destination = target / relative
                    record = {
                        "s3_bucket": bucket,
                        "s3_key": key,
                        "etag": obj["ETag"],
                        "size": obj["Size"],
                        "destination": str(destination),
                    }
                    local_file = staging / relative
                    try:
                        if not destination.resolve().is_relative_to(target):
                            raise ValueError("Destination resolves outside the Empatica target directory.")
                        previous = saved.get((bucket, key), {})
                        same_revision = all(previous.get(name) == value for name, value in record.items())
                        if same_revision and self.matches_destination(destination, previous):
                            continue
                        self.download_object(client, record, local_file)
                    except (BotoCoreError, ClientError, OSError, ValueError) as error:
                        failures.append({
                            **record,
                            "filename": str(destination),
                            "type": "checker failure",
                            "error": str(error),
                            "timestamp": time.time(),
                        })
                    else:
                        filename = str(local_file)
                        self._staged[filename] = record
                        tasks.append(filename)
        if failures:
            self.warning(f"Empatica failed to download {len(failures)} object(s). See upload state.")
        return {"to do": tasks, "failure": failures}

    @staticmethod
    def matches_destination(destination, previous):
        try:
            info = destination.stat()
        except FileNotFoundError:
            return False
        return (
            stat.S_ISREG(info.st_mode)
            and info.st_size == previous["size"]
            and info.st_mtime_ns == previous.get("mtime_ns")
        )

    @staticmethod
    def download_object(client, record, local_file):
        """Download the exact revision seen during listing into private staging."""
        local_file.parent.mkdir(parents=True, exist_ok=True)
        response = client.get_object(
            Bucket=record["s3_bucket"], Key=record["s3_key"], IfMatch=record["etag"]
        )
        with closing(response["Body"]) as body, local_file.open("xb") as output:
            shutil.copyfileobj(body, output)
        if local_file.stat().st_size != record["size"]:
            raise OSError("Downloaded size differs from the S3 listing.")

    def load_state(self):
        try:
            return super().load_state()
        except FileNotFoundError:
            return {category: [] for category in EMPTY_LOG}

    def write_state(self, state_data):
        directory = Path(self.state_path)
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as output:
            temporary = Path(output.name)
            try:
                json.dump(state_data, output, indent=2)
                output.close()
                temporary.replace(directory / self.state_filename)
            finally:
                temporary.unlink(missing_ok=True)

    def save(self, completed):
        """Record only published revisions as successful and retain unresolved failures."""
        successes = {(item["s3_bucket"], item["s3_key"]): item for item in self._state["success"]}
        failures = {(item["s3_bucket"], item["s3_key"]): item for item in self._state["failure"]}
        for item in completed["success"]:
            record = self._staged[item["filename"]]
            identity = (record["s3_bucket"], record["s3_key"])
            successes[identity] = {
                **record,
                "filename": record["destination"],
                "mtime_ns": Path(record["destination"]).stat().st_mtime_ns,
                "timestamp": item["timestamp"],
            }
            failures.pop(identity, None)
        for item in completed["failure"]:
            record = self._staged.get(item["filename"], item)
            identity = (record["s3_bucket"], record["s3_key"])
            failures[identity] = {**item, **record, "filename": record["destination"]}
        self._state["success"] = list(successes.values())
        self._state["failure"] = list(failures.values())
        self.write_state(self._state)

    def clean(self):
        """The process context removes only its own staging directory."""
