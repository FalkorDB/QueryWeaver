"""Transport-security helpers shared by the app factory and the auth routes.

Both places decide whether to mark a cookie ``Secure``. Keeping a single
implementation here avoids the two copies drifting apart and silently
downgrading a cookie on a genuine HTTPS request.
"""

import os

from fastapi import Request


def is_secure_request(request: Request) -> bool:
    """Whether the request reached us over HTTPS.

    ``X-Forwarded-Proto`` wins when present, since TLS is normally terminated at
    a proxy. The header is normalized because proxies may append to an existing
    value (``"https, http"``) or use a different case (``"HTTPS"``); only the
    first hop - the one the browser actually spoke to - matters.
    """
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        return forwarded_proto.split(",")[0].strip().lower() == "https"

    return request.url.scheme == "https"


def should_mark_cookie_secure(request: Request) -> bool:
    """Whether a credential cookie must carry the ``Secure`` flag.

    Fail secure. Deriving the flag from the request alone downgrades the cookie
    for anyone who can steer a single request over plain HTTP, so the transport
    only gets a say in a local ``APP_ENV=development`` run - where a Secure
    cookie would be dropped over the plain HTTP that run serves.
    """
    app_env = os.getenv("APP_ENV")
    if app_env is not None and app_env.strip().lower() == "development":
        return is_secure_request(request)

    return True
