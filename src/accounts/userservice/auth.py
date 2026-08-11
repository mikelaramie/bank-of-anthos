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

"""JWT helpers for authenticated userservice endpoints."""

import jwt


def bearer_token_from_header(auth_header):
    """Extract bearer token from Authorization header."""
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header.split('Bearer ', 1)[1]
    return None


def decode_bearer_token(auth_header, public_key, algorithms=None):
    """Decode and verify JWT from Authorization header."""
    token = bearer_token_from_header(auth_header)
    if not token:
        raise PermissionError('missing bearer token')
    if algorithms is None:
        algorithms = ['RS256']
    return jwt.decode(token, key=public_key, algorithms=algorithms)
