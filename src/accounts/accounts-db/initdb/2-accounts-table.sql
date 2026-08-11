/*
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

CREATE TABLE IF NOT EXISTS accounts (
  accountid CHAR(10) PRIMARY KEY,
  username VARCHAR(64) NOT NULL,
  account_type VARCHAR(16) NOT NULL,
  nickname VARCHAR(64),
  CONSTRAINT fk_accounts_username
    FOREIGN KEY (username) REFERENCES users (username),
  CONSTRAINT uq_accounts_username_type UNIQUE (username, account_type)
);

CREATE INDEX IF NOT EXISTS idx_accounts_username ON accounts (username);

-- Backfill checking accounts from legacy users rows.
INSERT INTO accounts (accountid, username, account_type, nickname)
SELECT accountid, username, 'CHECKING', 'Checking'
FROM users
ON CONFLICT DO NOTHING;
