
import os
import sqlite3
import hashlib
import hmac
import secrets
import time

DB_PATH = os.environ.get(
    "JUSTEPARLER_DB_PATH",
    "justeparler_accounts.sqlite3"
)

ITERATIONS = 600000


def connect_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_salt BLOB NOT NULL,
            password_hash BLOB NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)
    db.commit()
    return db


def register(email, password):
    email = email.strip().casefold()

    if not 3 <= len(email) <= 254 or "@" not in email:
        raise ValueError("Adresse e-mail invalide")

    if len(password) < 12:
        raise ValueError(
            "Le mot de passe doit contenir 12 caractères minimum"
        )

    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        ITERATIONS
    )

    with connect_db() as db:
        try:
            cursor = db.execute(
                """
                INSERT INTO accounts
                (email, password_salt, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (email, salt, password_hash, int(time.time()))
            )
            db.commit()
            return cursor.lastrowid

        except sqlite3.IntegrityError:
            raise ValueError(
                "Cette adresse e-mail est déjà utilisée"
            )


def login(email, password):
    email = email.strip().casefold()

    with connect_db() as db:
        account = db.execute(
            """
            SELECT id, password_salt, password_hash
            FROM accounts
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if account is None:
            return None

        account_id, salt, stored_hash = account

        calculated_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            ITERATIONS
        )

        if not hmac.compare_digest(
            calculated_hash, stored_hash
        ):
            return None

        token = secrets.token_urlsafe(32)

        token_hash = hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

        expires_at = int(time.time()) + 86400

        db.execute(
            """
            INSERT INTO sessions
            (token_hash, account_id, expires_at)
            VALUES (?, ?, ?)
            """,
            (token_hash, account_id, expires_at)
        )

        db.commit()
        return token


def get_account(token):
    if not isinstance(token, str):
        return None

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    with connect_db() as db:
        account = db.execute(
            """
            SELECT accounts.id, accounts.email
            FROM sessions
            JOIN accounts
            ON sessions.account_id = accounts.id
            WHERE sessions.token_hash = ?
            AND sessions.expires_at > ?
            """,
            (token_hash, int(time.time()))
        ).fetchone()

        if account is None:
            return None

        return {
            "id": account[0],
            "email": account[1]
        }


def logout(token):
    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    with connect_db() as db:
        db.execute(
            "DELETE FROM sessions WHERE token_hash = ?",
            (token_hash,)
        )
        db.commit()
      
