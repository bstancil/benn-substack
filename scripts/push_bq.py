#!/usr/bin/env python3
"""
Push the DuckDB tables to BigQuery.

BigQuery is a downstream sink, not a source of truth — every run fully
replaces each table with the current DuckDB contents (same disposable
philosophy as the local DB).

Config in .env:
  BQ_DATASET   dataset name to load into (unset = skip this step entirely)
  BQ_PROJECT   optional; defaults to the service account's own project

Auth reuses data/service-account.json (see README). The service account
needs the BigQuery API enabled and, on the target project, the
"BigQuery Data Editor" and "BigQuery Job User" roles.
"""

import json
import tempfile
from pathlib import Path

import duckdb

from substack_api import ROOT_DIR, load_env

DB_PATH = ROOT_DIR / "data" / "substack.duckdb"
SERVICE_ACCOUNT_PATH = ROOT_DIR / "data" / "service-account.json"

# DuckDB views are materialized as ordinary BQ tables
TABLES = [
    "posts",
    "post_content",
    "post_stats",
    "post_stats_history",
    "post_engagement",
    "post_engagement_history",
    "posts_overview",
    "subscriber_timeseries",
    "traffic_daily",
    "visitor_sources_monthly",
    "subscribers",
    "subscriber_sources",
    "subscriber_events",
]


def push_bq():
    dataset = load_env("BQ_DATASET")
    if not dataset:
        print("BigQuery push: BQ_DATASET not set in .env — skipping")
        return 0
    if not SERVICE_ACCOUNT_PATH.exists():
        print(f"BigQuery push: {SERVICE_ACCOUNT_PATH} missing — skipping")
        return 0

    from google.cloud import bigquery
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_PATH),
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    project = load_env("BQ_PROJECT") or json.loads(
        SERVICE_ACCOUNT_PATH.read_text()
    )["project_id"]
    client = bigquery.Client(project=project, credentials=creds)
    client.create_dataset(f"{project}.{dataset}", exists_ok=True)

    con = duckdb.connect(str(DB_PATH), read_only=True)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    try:
        with tempfile.TemporaryDirectory() as tmp:
            for table in TABLES:
                parquet = Path(tmp) / f"{table}.parquet"
                con.execute(
                    f"COPY (SELECT * FROM {table}) TO '{parquet}' (FORMAT PARQUET)"
                )
                with open(parquet, "rb") as f:
                    job = client.load_table_from_file(
                        f, f"{project}.{dataset}.{table}", job_config=job_config
                    )
                job.result()
                print(f"  {project}.{dataset}.{table}: {job.output_rows} rows")
    finally:
        con.close()

    print(f"BigQuery push complete: {len(TABLES)} tables -> {project}.{dataset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(push_bq())
