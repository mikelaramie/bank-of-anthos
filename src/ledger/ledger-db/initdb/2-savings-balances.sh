#!/bin/bash
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

# Seed demo balances for savings accounts.

set -u

if [ -z "$USE_DEMO_DATA" ] && [ "$USE_DEMO_DATA" != "True" ]; then
    echo "\$USE_DEMO_DATA not \"True\"; no savings balances added"
    exit 0
fi

readonly ENV_VARS=(
  "POSTGRES_DB"
  "POSTGRES_USER"
  "POSTGRES_PASSWORD"
  "LOCAL_ROUTING_NUM"
)

add_transaction() {
    DATE=$(date -u +"%Y-%m-%d %H:%M:%S.%3N%z")
    echo "adding savings deposit: $1 -> $2"
    PGPASSWORD="$POSTGRES_PASSWORD" psql -X -v ON_ERROR_STOP=1 \
        -v fromacct="$1" -v toacct="$2" -v fromroute="$3" -v toroute="$4" -v amount="$5" \
        --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        INSERT INTO TRANSACTIONS (FROM_ACCT, TO_ACCT, FROM_ROUTE, TO_ROUTE, AMOUNT, TIMESTAMP)
        VALUES (:'fromacct', :'toacct', :'fromroute', :'toroute', :'amount', '$DATE');
EOSQL
}

seed_savings_balances() {
    EXTERNAL_ACCOUNT="9099791699"
    EXTERNAL_ROUTING="808889588"
    SAVINGS_ACCOUNTS=("1011226222" "1033623444" "1055757666" "1077441388")
    INITIAL_DEPOSIT=50000

    for account in "${SAVINGS_ACCOUNTS[@]}"; do
        add_transaction "$EXTERNAL_ACCOUNT" "$account" "$EXTERNAL_ROUTING" \
            "$LOCAL_ROUTING_NUM" $INITIAL_DEPOSIT
    done
}

main() {
    for env_var in ${ENV_VARS[@]}; do
        if [[ -z "${!env_var}" ]]; then
            echo "Error: environment variable '$env_var' not set. Aborting."
            exit 1
        fi
    done
    seed_savings_balances
}

main
