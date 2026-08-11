# Copyright 2021 Google LLC
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
Userservice manages user account creation, user login, and related tasks
"""

import atexit
from datetime import datetime, timedelta
import logging
import os
import sys
import re

import bcrypt
import jwt
from flask import Flask, jsonify, request
import bleach
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from opentelemetry import trace
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.propagate import set_global_textmap
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator
from opentelemetry.instrumentation.flask import FlaskInstrumentor

from auth import decode_bearer_token
from db import ACCOUNT_TYPE_SAVINGS, UserDb
from secrets import resolve_accounts_db_uri


def _build_token(app, username, user, active_accountid):
    """Create a signed JWT for the user and active account."""
    full_name = '{} {}'.format(user['firstname'], user['lastname'])
    exp_time = datetime.utcnow() + timedelta(seconds=app.config['EXPIRY_SECONDS'])
    account_ids = [
        account['accountid'] for account in users_db.get_accounts(username)
    ]
    if active_accountid not in account_ids:
        account_ids.append(active_accountid)
    payload = {
        'user': username,
        'acct': active_accountid,
        'accounts': account_ids,
        'name': full_name,
        'iat': datetime.utcnow(),
        'exp': exp_time,
    }
    return jwt.encode(payload, app.config['PRIVATE_KEY'], algorithm='RS256')


def create_app():
    """Flask application factory to create instances
    of the Userservice Flask App
    """
    app = Flask(__name__)

    # Disabling unused-variable for lines with route decorated functions
    # as pylint thinks they are unused
    # pylint: disable=unused-variable

    @app.route('/version', methods=['GET'])
    def version():
        """
        Service version endpoint
        """
        return app.config['VERSION'], 200

    @app.route('/ready', methods=['GET'])
    def readiness():
        """
        Readiness probe
        """
        return 'ok', 200

    @app.route('/users', methods=['POST'])
    def create_user():
        """Create a user record with a checking account.

        Optional form field ``open_savings`` (true/1/on) also opens a savings account.
        """
        try:
            app.logger.debug('Sanitizing input.')
            req = {k: bleach.clean(v) for k, v in request.form.items()}
            __validate_new_user(req)
            if users_db.get_user(req['username']) is not None:
                raise NameError('user {} already exists'.format(req['username']))

            app.logger.debug("Creating password hash.")
            password = req['password']
            salt = bcrypt.gensalt()
            passhash = bcrypt.hashpw(password.encode('utf-8'), salt)

            accountid = users_db.generate_accountid()
            open_savings = req.get('open_savings', '').lower() in ('true', '1', 'on', 'yes')

            user_data = {
                'accountid': accountid,
                'username': req['username'],
                'passhash': passhash,
                'firstname': req['firstname'],
                'lastname': req['lastname'],
                'birthday': req['birthday'],
                'timezone': req['timezone'],
                'address': req['address'],
                'state': req['state'],
                'zip': req['zip'],
                'ssn': req['ssn'],
            }
            app.logger.debug("Adding user to the database")
            users_db.add_user(user_data, open_savings=open_savings)
            app.logger.info("Successfully created user.")

            accounts = users_db.get_accounts(req['username'])
            return jsonify({'accounts': accounts}), 201

        except UserWarning as warn:
            app.logger.error("Error creating new user: %s", str(warn))
            return str(warn), 400
        except NameError as err:
            app.logger.error("Error creating new user: %s", str(err))
            return str(err), 409
        except SQLAlchemyError as err:
            app.logger.error("Error creating new user: %s", str(err))
            return 'failed to create user', 500

    @app.route('/users/<username>/accounts', methods=['GET'])
    def list_accounts(username):
        """List bank accounts for the authenticated user."""
        username = bleach.clean(username)
        try:
            token = decode_bearer_token(
                request.headers.get('Authorization'),
                app.config['PUBLIC_KEY'],
            )
            if token['user'] != username:
                raise PermissionError('not authorized')
            accounts = users_db.get_accounts(username)
            return jsonify({'accounts': accounts}), 200
        except PermissionError as err:
            app.logger.error('Error listing accounts: %s', str(err))
            return str(err), 401
        except jwt.exceptions.PyJWTError as err:
            app.logger.error('Error listing accounts: %s', str(err))
            return 'not authorized', 401
        except SQLAlchemyError as err:
            app.logger.error('Error listing accounts: %s', str(err))
            return 'failed to list accounts', 500

    @app.route('/users/<username>/accounts', methods=['POST'])
    def open_account(username):
        """Open a savings account for the authenticated user."""
        username = bleach.clean(username)
        try:
            token = decode_bearer_token(
                request.headers.get('Authorization'),
                app.config['PUBLIC_KEY'],
            )
            if token['user'] != username:
                raise PermissionError('not authorized')

            req = request.get_json(silent=True) or {}
            account_type = bleach.clean(req.get('account_type', ACCOUNT_TYPE_SAVINGS))
            nickname = bleach.clean(req.get('nickname', 'Savings'))
            accountid = users_db.add_account(username, account_type, nickname)
            account = {
                'accountid': accountid,
                'username': username,
                'account_type': account_type,
                'nickname': nickname,
            }
            return jsonify(account), 201
        except PermissionError as err:
            app.logger.error('Error opening account: %s', str(err))
            return str(err), 401
        except NameError as err:
            app.logger.error('Error opening account: %s', str(err))
            return str(err), 409
        except ValueError as err:
            app.logger.error('Error opening account: %s', str(err))
            return str(err), 400
        except jwt.exceptions.PyJWTError as err:
            app.logger.error('Error opening account: %s', str(err))
            return 'not authorized', 401
        except SQLAlchemyError as err:
            app.logger.error('Error opening account: %s', str(err))
            return 'failed to open account', 500

    @app.route('/users/switch-account', methods=['POST'])
    def switch_account():
        """Re-issue JWT with a new active account for the authenticated user."""
        try:
            token = decode_bearer_token(
                request.headers.get('Authorization'),
                app.config['PUBLIC_KEY'],
            )
            username = token['user']
            req = request.get_json(silent=True) or {}
            accountid = bleach.clean(req.get('accountid', ''))
            if not accountid:
                raise UserWarning('accountid is required')
            if not users_db.user_owns_account(username, accountid):
                raise PermissionError('not authorized')

            user = users_db.get_user(username)
            if user is None:
                raise LookupError('user {} does not exist'.format(username))

            new_token = _build_token(app, username, user, accountid)
            return jsonify({'token': new_token}), 200
        except UserWarning as warn:
            app.logger.error('Error switching account: %s', str(warn))
            return str(warn), 400
        except PermissionError as err:
            app.logger.error('Error switching account: %s', str(err))
            return str(err), 401
        except LookupError as err:
            app.logger.error('Error switching account: %s', str(err))
            return str(err), 404
        except jwt.exceptions.PyJWTError as err:
            app.logger.error('Error switching account: %s', str(err))
            return 'not authorized', 401
        except SQLAlchemyError as err:
            app.logger.error('Error switching account: %s', str(err))
            return 'failed to switch account', 500

    def __validate_new_user(req):
        app.logger.debug('validating create user request: %s', str(req))
        fields = (
            'username',
            'password',
            'password-repeat',
            'firstname',
            'lastname',
            'birthday',
            'timezone',
            'address',
            'state',
            'zip',
            'ssn',
        )
        if any(f not in req for f in fields):
            raise UserWarning('missing required field(s)')
        if any(not bool(req[f] or req[f].strip()) for f in fields):
            raise UserWarning('missing value for input field(s)')

        if not re.match(r"\A[a-zA-Z0-9_]{2,15}\Z", req['username']):
            raise UserWarning(
                'username must contain 2-15 alphanumeric characters or underscores'
            )
        if not req['password'] == req['password-repeat']:
            raise UserWarning('passwords do not match')

    @app.route('/login', methods=['GET'])
    def login():
        """Login a user and return a JWT token."""
        app.logger.debug('Sanitizing login input.')
        username = bleach.clean(request.args.get('username'))
        password = bleach.clean(request.args.get('password'))

        try:
            app.logger.debug('Getting the user data.')
            user = users_db.get_user(username)
            if user is None:
                raise LookupError('user {} does not exist'.format(username))

            app.logger.debug('Validating the password.')
            if not bcrypt.checkpw(password.encode('utf-8'), user['passhash']):
                raise PermissionError('invalid login')

            active_accountid = users_db.get_default_accountid(username)
            token = _build_token(app, username, user, active_accountid)
            app.logger.info('Login Successful.')
            return jsonify({'token': token}), 200

        except LookupError as err:
            app.logger.error('Error logging in: %s', str(err))
            return str(err), 404
        except PermissionError as err:
            app.logger.error('Error logging in: %s', str(err))
            return str(err), 401
        except SQLAlchemyError as err:
            app.logger.error('Error logging in: %s', str(err))
            return 'failed to retrieve user information', 500

    @atexit.register
    def _shutdown():
        """Executed when web app is terminated."""
        app.logger.info("Stopping userservice.")

    app.logger.handlers = logging.getLogger('gunicorn.error').handlers
    app.logger.setLevel(logging.getLogger('gunicorn.error').level)
    app.logger.info('Starting userservice.')

    if os.environ['ENABLE_TRACING'] == "true":
        app.logger.info("✅ Tracing enabled.")
        trace.set_tracer_provider(TracerProvider())
        cloud_trace_exporter = CloudTraceSpanExporter()
        trace.get_tracer_provider().add_span_processor(
            BatchSpanProcessor(cloud_trace_exporter)
        )
        set_global_textmap(CloudTraceFormatPropagator())
        FlaskInstrumentor().instrument_app(app)
    else:
        app.logger.info("🚫 Tracing disabled.")

    app.config['VERSION'] = os.environ.get('VERSION')
    app.config['EXPIRY_SECONDS'] = int(os.environ.get('TOKEN_EXPIRY_SECONDS'))
    app.config['PRIVATE_KEY'] = open(os.environ.get('PRIV_KEY_PATH'), 'r').read()
    app.config['PUBLIC_KEY'] = open(os.environ.get('PUB_KEY_PATH'), 'r').read()

    try:
        users_db = UserDb(resolve_accounts_db_uri(app.logger), app.logger)
    except OperationalError:
        app.logger.critical("users_db database connection failed")
        sys.exit(1)
    return app


if __name__ == "__main__":
    USERSERVICE = create_app()
    USERSERVICE.run()
