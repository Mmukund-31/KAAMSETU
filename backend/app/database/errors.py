"""Driver-independent inspection of PostgreSQL errors.

pg8000 raises IntegrityError only for unique violations (23505); foreign-key (23503) and
check violations surface as ProgrammingError. Services therefore decide by SQLSTATE,
not by exception class.
"""

from sqlalchemy.exc import DBAPIError

UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"


def sqlstate(exc: BaseException) -> str | None:
    orig = getattr(exc, "orig", exc) if isinstance(exc, DBAPIError) else exc
    # pg8000 puts the server's error fields dict in args[0]; psycopg exposes .sqlstate.
    code = getattr(orig, "sqlstate", None)
    if code:
        return code
    args = getattr(orig, "args", ())
    if args and isinstance(args[0], dict):
        return args[0].get("C")
    return None


def constraint_name(exc: BaseException) -> str | None:
    orig = getattr(exc, "orig", exc)
    args = getattr(orig, "args", ())
    if args and isinstance(args[0], dict):
        return args[0].get("n")
    return None
