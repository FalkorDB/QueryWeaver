"""Transport-security helpers shared by the app factory and the auth routes.

Both places decide whether to mark a cookie ``Secure``. Keeping a single
implementation here avoids the two copies drifting apart and silently
downgrading a cookie on a genuine HTTPS request.
"""

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
