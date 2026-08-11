# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Fetch database credentials from Google Cloud Secret Manager."""

import json
import logging
import os

from google.cloud import secretmanager

LOGGER = logging.getLogger(__name__)


def _secret_resource_name(secret_id: str) -> str:
    project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise ValueError("GCP_PROJECT or GOOGLE_CLOUD_PROJECT must be set")
    return f"projects/{project_id}/secrets/{secret_id}/versions/latest"


def access_secret(secret_id: str) -> str:
    """Return the UTF-8 payload for the latest secret version."""
    client = secretmanager.SecretManagerServiceClient()
    response = client.access_secret_version(request={"name": _secret_resource_name(secret_id)})
    return response.payload.data.decode("UTF-8")


def resolve_accounts_db_uri(logger: logging.Logger = LOGGER) -> str:
    """
    Resolve the accounts database URI.

    Uses Secret Manager when ACCOUNTS_DB_SECRET_ID is set. Falls back to
    ACCOUNTS_DB_URI for local development and unit tests.
    """
    secret_id = os.environ.get("ACCOUNTS_DB_SECRET_ID")
    if not secret_id:
        uri = os.environ.get("ACCOUNTS_DB_URI")
        if uri:
            logger.info("Using ACCOUNTS_DB_URI from environment (local fallback).")
            return uri
        raise ValueError("ACCOUNTS_DB_SECRET_ID or ACCOUNTS_DB_URI must be set")

    logger.info("Loading accounts database credentials from Secret Manager.")
    payload = access_secret(secret_id)
    try:
        data = json.loads(payload)
        uri = data.get("uri")
        if uri:
            return uri
    except json.JSONDecodeError:
        pass

    # Allow storing the full URI as plain secret text.
    return payload.strip()
