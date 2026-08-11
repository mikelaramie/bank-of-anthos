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

"""Tests for Secret Manager credential resolution."""

import os
import unittest
from unittest.mock import patch

from secrets import resolve_accounts_db_uri


class TestSecrets(unittest.TestCase):
    """Tests for secrets module."""

    def test_resolve_accounts_db_uri_local_fallback(self):
        with patch.dict(os.environ, {"ACCOUNTS_DB_URI": "sqlite:///:memory:"}, clear=True):
            self.assertEqual(resolve_accounts_db_uri(), "sqlite:///:memory:")

    @patch("secrets.access_secret")
    def test_resolve_accounts_db_uri_from_secret_json(self, mock_access):
        mock_access.return_value = '{"uri":"postgresql://u:p@db:5432/db"}'
        with patch.dict(
            os.environ,
            {
                "ACCOUNTS_DB_SECRET_ID": "accounts-db-credentials-development",
                "GCP_PROJECT": "bank-of-anthos-ci",
            },
            clear=True,
        ):
            self.assertEqual(
                resolve_accounts_db_uri(),
                "postgresql://u:p@db:5432/db",
            )
