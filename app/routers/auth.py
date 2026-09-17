import re

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app import auth, crud, database, models, schemas, security

router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="app/templates")

# Roles offered on the sign-up page, in display order
SIGNUP_ROLES = [
    {"value": models.Role.ADMIN, "label": "Administrator",
     "description": "Manage stations, substations, users and reports",
     "note": "Needs approval"},
    {"value": models.Role.OPERATOR, "label": "Operator",
     "description": "Register consumers, verify alerts and dispatch technicians"},
    {"value": models.Role.TECHNICIAN, "label": "Technician",
     "description": "Accept maintenance jobs and update repair status"},
]
USERNAME_PATTERN = re.compile(r"[a-z0-9._-]{3,30}")
MIN_PASSWORD_LENGTH = 8
SIGNED_UP_SESSION_KEY = "signed_up"  # {"username": ..., "pending": bool}, shown once on /login


def normalize_username(username: str) -> str:
    """Usernames are case-insensitive: stored and looked up in lowercase."""
    return username.strip().lower()


def render_login(request: Request, next_url: str | None, username: str = "", error: str | None = None,
                 notice: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "title": "Sign in · PGMS",
            "active_tab": "login",
            "next": auth.safe_next_url(next_url),
            "username": username,
            "error": error,
            "notice": notice,
        },
        status_code=status_code,
    )


def render_signup(request: Request, role: str = "", name: str = "", username: str = "",
                  errors: dict[str, str] | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "signup.html",
        {
            "title": "Sign up · PGMS",
            "active_tab": "signup",
            "roles": SIGNUP_ROLES,
            "role": role,
            "name": name,
            "username": username,
            "errors": errors or {},
        },
        status_code=status_code,
    )


def validate_signup(db: Session, role: str, name: str, username: str, password: str,
                    confirm_password: str) -> dict[str, str]:
    """Return {field: message} for every invalid field; empty when the form is valid."""
    errors = {}
    if role not in {r["value"] for r in SIGNUP_ROLES}:
        errors["role"] = "Choose what kind of user you are."

    if not name:
        errors["name"] = "Enter your full name."
    elif len(name) > 100:
        errors["name"] = "Name must be 100 characters or fewer."

    if not USERNAME_PATTERN.fullmatch(username):
        errors["username"] = "Use 3–30 characters: letters, numbers, dots, underscores or hyphens."
    elif crud.get_user_by_username(db, username):
        errors["username"] = "That username is already taken."

    if (len(password) < MIN_PASSWORD_LENGTH
            or not re.search(r"[A-Za-z]", password)
            or not re.search(r"\d", password)):
        errors["password"] = "Use at least 8 characters, with a letter and a number."
    elif len(password.encode("utf-8")) > security.MAX_PASSWORD_BYTES:
        errors["password"] = f"Password is too long ({security.MAX_PASSWORD_BYTES} bytes max)."
    elif password != confirm_password:
        errors["confirm_password"] = "Passwords don't match."
    return errors


@router.get("/login")
def login_page(request: Request, next: str | None = None, logged_out: bool = False,
               user=Depends(auth.get_current_user)):
    if user is not None:
        return RedirectResponse(url=auth.dashboard_for(user), status_code=303)

    signed_up = request.session.pop(SIGNED_UP_SESSION_KEY, None)
    if isinstance(signed_up, dict):
        if signed_up.get("pending"):
            notice = ("Request sent. An existing administrator must approve your account "
                      "before you can sign in.")
        else:
            notice = "Account created. Sign in with your new username and password."
        return render_login(request, next, signed_up.get("username", ""), notice=notice)
    notice = "You have been signed out." if logged_out else None
    return render_login(request, next, notice=notice)


@router.post("/login")
def login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str | None = Form(None),
    db: Session = Depends(database.get_db)
):
    username = normalize_username(username)
    if not username or not password:
        return render_login(request, next, username, error="Enter your username and password.", status_code=400)

    user = auth.authenticate(db, username, password)
    if user is None:
        crud.log_action(db, "LOGIN_FAILED", f"Failed sign-in attempt for username '{username[:50]}'")
        return render_login(request, next, username, error="Invalid username or password.", status_code=401)

    if user.approvalStatus == models.ApprovalStatus.PENDING:
        crud.log_action(db, "LOGIN_PENDING", f"'{user.username}' tried to sign in before approval", user.userID)
        return render_login(request, next, username, status_code=403,
                            error="Your administrator account is waiting for approval by an existing administrator.")

    if user.approvalStatus == models.ApprovalStatus.REJECTED:
        crud.log_action(db, "LOGIN_BLOCKED", f"Rejected account '{user.username}' tried to sign in", user.userID)
        return render_login(request, next, username, status_code=403,
                            error="Your administrator account request was declined. Contact an administrator.")

    if not user.isActive:
        crud.log_action(db, "LOGIN_BLOCKED", f"Deactivated account '{user.username}' tried to sign in", user.userID)
        return render_login(request, next, username,
                            error="This account has been deactivated. Contact your administrator.", status_code=403)

    auth.login_user(request, user)
    crud.log_action(db, "LOGIN", f"{user.username} signed in as {user.role}", user.userID)
    return RedirectResponse(url=auth.safe_next_url(next) or auth.dashboard_for(user), status_code=303)


@router.get("/signup")
def signup_page(request: Request, user=Depends(auth.get_current_user)):
    if user is not None:
        return RedirectResponse(url=auth.dashboard_for(user), status_code=303)
    return render_signup(request)


@router.post("/signup")
def signup(
    request: Request,
    role: str = Form(""),
    name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
    db: Session = Depends(database.get_db)
):
    name = name.strip()
    username = normalize_username(username)
    errors = validate_signup(db, role, name, username, password, confirm_password)
    if errors:
        return render_signup(request, role, name, username, errors, status_code=400)

    # Administrator sign-ups wait for an existing admin, unless there is none yet to approve them
    needs_approval = role == models.Role.ADMIN and crud.has_approved_admin(db)
    new_user = schemas.UserAccountCreate(
        username=username,
        password=password,
        role=role,
        name=name,
        approvalStatus=models.ApprovalStatus.PENDING if needs_approval else models.ApprovalStatus.APPROVED,
        availabilityStatus="AVAILABLE" if role == models.Role.TECHNICIAN else None,
    )
    try:
        user = crud.create_user(db, new_user)
    except IntegrityError:  # the username was taken between the check above and the insert
        db.rollback()
        return render_signup(request, role, name, username,
                             {"username": "That username is already taken."}, status_code=400)

    if needs_approval:
        crud.log_action(db, "SIGNUP", f"{user.username} requested an ADMIN account (awaiting approval)", user.userID)
    else:
        crud.log_action(db, "SIGNUP", f"{user.username} created a {user.role} account", user.userID)
    request.session[SIGNED_UP_SESSION_KEY] = {"username": user.username, "pending": needs_approval}
    return RedirectResponse(url="/login", status_code=303)


@router.post("/logout")
def logout(request: Request, user=Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    if user is not None:
        crud.log_action(db, "LOGOUT", f"{user.username} signed out", user.userID)
    auth.logout_user(request)
    return RedirectResponse(url="/login?logged_out=1", status_code=303)
