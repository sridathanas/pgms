from fastapi import Depends, Request
from sqlalchemy.orm import Session
from app import crud, database, models, security

SESSION_USER_KEY = "user_id"

# Where each role lands after signing in (matches the login flowchart)
DASHBOARDS = {
    models.Role.ADMIN: "/admin/",
    models.Role.OPERATOR: "/operator/",
    models.Role.TECHNICIAN: "/technician/",
}

# Checked against when the username doesn't exist, so unknown and known usernames take the same time
_DUMMY_HASH = security.hash_password("pgms-timing-placeholder")


class LoginRequired(Exception):
    """No signed-in user. main.py turns this into a redirect to /login."""
    def __init__(self, next_url: str | None = None):
        self.next_url = next_url


class RoleForbidden(Exception):
    """Signed in, but the role isn't allowed here. main.py turns this into a 403 page."""
    def __init__(self, user: models.UserAccount):
        self.user = user


def authenticate(db: Session, username: str, password: str):
    """Return the user if the username and password match, else None. Does not check isActive."""
    user = crud.get_user_by_username(db, username)
    if user is None:
        security.verify_password(password, _DUMMY_HASH)
        return None
    if not security.verify_password(password, user.passwordHash):
        return None
    return user


def login_user(request: Request, user: models.UserAccount):
    request.session.clear()
    request.session[SESSION_USER_KEY] = user.userID


def logout_user(request: Request):
    request.session.clear()


def dashboard_for(user: models.UserAccount) -> str:
    return DASHBOARDS.get(user.role, "/login")


def safe_next_url(next_url: str | None) -> str | None:
    """Only allow redirects to paths on this site, never to another host."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url:
        return next_url
    return None


def get_current_user(request: Request, db: Session = Depends(database.get_db)):
    """The signed-in user, or None. Re-read from the database so deactivation takes effect immediately."""
    user_id = request.session.get(SESSION_USER_KEY)
    if user_id is None:
        return None
    user = crud.get_user(db, user_id)
    if user is None or not user.isActive or user.approvalStatus != models.ApprovalStatus.APPROVED:
        request.session.clear()
        return None
    return user


def require_login(request: Request, user: models.UserAccount | None = Depends(get_current_user)):
    if user is None:
        # Only GET pages can be returned to after signing in; a form POST would hit a GET-less route
        next_url = str(request.url.path) if request.method == "GET" else None
        if next_url and request.url.query:
            next_url += "?" + request.url.query
        raise LoginRequired(next_url)
    request.state.user = user  # lets base.html show who is signed in
    return user


def require_roles(*roles: str):
    """Router/route dependency: allow only signed-in users whose role is in `roles`."""
    def dependency(user: models.UserAccount = Depends(require_login)):
        if user.role not in roles:
            raise RoleForbidden(user)
        return user
    return dependency
