# Copyright 2019 Google LLC
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

"""
db manages interactions with the underlying database
"""

import logging
import random
from sqlalchemy import create_engine, MetaData, Table, Column, String, Date, LargeBinary
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

ACCOUNT_TYPE_CHECKING = 'CHECKING'
ACCOUNT_TYPE_SAVINGS = 'SAVINGS'
VALID_ACCOUNT_TYPES = {ACCOUNT_TYPE_CHECKING, ACCOUNT_TYPE_SAVINGS}


class UserDb:
    """
    UserDb provides a set of helper functions over SQLAlchemy
    to handle db operations for userservice
    """

    def __init__(self, uri, logger=logging):
        self.engine = create_engine(uri)
        self.logger = logger
        metadata = MetaData(self.engine)
        self.users_table = Table(
            'users',
            metadata,
            Column('accountid', String, primary_key=True),
            Column('username', String, unique=True, nullable=False),
            Column('passhash', LargeBinary, nullable=False),
            Column('firstname', String, nullable=False),
            Column('lastname', String, nullable=False),
            Column('birthday', Date, nullable=False),
            Column('timezone', String, nullable=False),
            Column('address', String, nullable=False),
            Column('state', String, nullable=False),
            Column('zip', String, nullable=False),
            Column('ssn', String, nullable=False),
        )
        self.accounts_table = Table(
            'accounts',
            metadata,
            Column('accountid', String, primary_key=True),
            Column('username', String, nullable=False),
            Column('account_type', String, nullable=False),
            Column('nickname', String),
        )

        # Set up tracing autoinstrumentation for sqlalchemy
        SQLAlchemyInstrumentor().instrument(
            engine=self.engine,
            service='users',
        )

    def add_user(self, user, open_savings=False):
        """Add a user and their bank accounts in one transaction.

        Creates a CHECKING account (stored on users.accountid for compatibility)
        and optionally a SAVINGS account.
        """
        checking_id = user['accountid']
        with self.engine.begin() as conn:
            statement = self.users_table.insert().values(user)
            self.logger.debug('QUERY: %s', str(statement))
            conn.execute(statement)

            checking = {
                'accountid': checking_id,
                'username': user['username'],
                'account_type': ACCOUNT_TYPE_CHECKING,
                'nickname': 'Checking',
            }
            statement = self.accounts_table.insert().values(checking)
            self.logger.debug('QUERY: %s', str(statement))
            conn.execute(statement)

            if open_savings:
                savings_id = self._generate_unique_accountid(conn)
                savings = {
                    'accountid': savings_id,
                    'username': user['username'],
                    'account_type': ACCOUNT_TYPE_SAVINGS,
                    'nickname': 'Savings',
                }
                statement = self.accounts_table.insert().values(savings)
                self.logger.debug('QUERY: %s', str(statement))
                conn.execute(statement)

    def add_account(self, username, account_type, nickname=None):
        """Open a new account for an existing user."""
        if account_type not in VALID_ACCOUNT_TYPES:
            raise ValueError('invalid account type')
        if nickname is None:
            nickname = account_type.title()
        with self.engine.begin() as conn:
            if self._get_account_by_type(conn, username, account_type) is not None:
                raise NameError(
                    '{} account already exists for {}'.format(account_type, username)
                )
            accountid = self._generate_unique_accountid(conn)
            account = {
                'accountid': accountid,
                'username': username,
                'account_type': account_type,
                'nickname': nickname,
            }
            statement = self.accounts_table.insert().values(account)
            self.logger.debug('QUERY: %s', str(statement))
            conn.execute(statement)
        return accountid

    def generate_accountid(self):
        """Generates a globally unique account id."""
        self.logger.debug('Generating an account ID')
        with self.engine.connect() as conn:
            return self._generate_unique_accountid(conn)

    def _generate_unique_accountid(self, conn):
        accountid = None
        while accountid is None:
            accountid = str(random.randint(1_000_000_000, (10_000_000_000 - 1)))
            if self._accountid_exists(conn, accountid):
                accountid = None
                self.logger.debug('RESULT: account ID already exists. Trying again')
        self.logger.debug('RESULT: account ID generated.')
        return accountid

    def _accountid_exists(self, conn, accountid):
        user_stmt = self.users_table.select().where(
            self.users_table.c.accountid == accountid
        )
        account_stmt = self.accounts_table.select().where(
            self.accounts_table.c.accountid == accountid
        )
        return (
            conn.execute(user_stmt).first() is not None
            or conn.execute(account_stmt).first() is not None
        )

    def get_user(self, username):
        """Get user data for the specified username."""
        statement = self.users_table.select().where(
            self.users_table.c.username == username
        )
        self.logger.debug('QUERY: %s', str(statement))
        with self.engine.connect() as conn:
            result = conn.execute(statement).first()
        self.logger.debug('RESULT: fetched user data for %s', username)
        return dict(result) if result is not None else None

    def get_accounts(self, username):
        """Return all bank accounts owned by the user."""
        statement = (
            self.accounts_table.select()
            .where(self.accounts_table.c.username == username)
            .order_by(self.accounts_table.c.account_type)
        )
        self.logger.debug('QUERY: %s', str(statement))
        with self.engine.connect() as conn:
            results = conn.execute(statement).fetchall()
        accounts = [dict(row) for row in results]
        self.logger.debug('RESULT: fetched %d accounts for %s', len(accounts), username)
        return accounts

    def get_default_accountid(self, username):
        """Return the user's primary checking account id."""
        with self.engine.connect() as conn:
            account = self._get_account_by_type(conn, username, ACCOUNT_TYPE_CHECKING)
        if account is not None:
            return account['accountid']
        user = self.get_user(username)
        if user is None:
            return None
        return user['accountid']

    def user_owns_account(self, username, accountid):
        """Return True if accountid belongs to username."""
        statement = self.accounts_table.select().where(
            (self.accounts_table.c.username == username)
            & (self.accounts_table.c.accountid == accountid)
        )
        with self.engine.connect() as conn:
            result = conn.execute(statement).first()
        return result is not None

    def _get_account_by_type(self, conn, username, account_type):
        statement = self.accounts_table.select().where(
            (self.accounts_table.c.username == username)
            & (self.accounts_table.c.account_type == account_type)
        )
        result = conn.execute(statement).first()
        return dict(result) if result is not None else None
