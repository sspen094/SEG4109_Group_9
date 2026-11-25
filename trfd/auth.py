"""Role-based access for the web layer (TR6).

executive: read-only dashboard
staff:     also overrides sentiment scores and tags
admin:     also manages users, data sources and alert thresholds
"""
from functools import wraps

from flask import abort, g, jsonify, redirect, request, url_for

RANK = {"executive": 1, "staff": 2, "admin": 3}


def can(user, role):
    return user is not None and RANK.get(user["role"], 0) >= RANK[role]


def require(role="executive"):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = g.get("user")
            if user is None:
                if request.path.startswith("/api/"):
                    return jsonify(error="Sign in required."), 401
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            if not can(user, role):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
