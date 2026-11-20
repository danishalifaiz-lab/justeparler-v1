
import json
import os
import secrets
import time
import threading

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path

import justeparler_auth as auth

lock = threading.RLock()
users = {}
reports = []


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            directory=str(Path(__file__).parent),
            **kwargs
        )

    def reply(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))

            if not 0 < length < 100000:
                return self.reply(
                    {"error": "Taille de requête invalide"}, 400
                )

            data = json.loads(self.rfile.read(length))

            if not isinstance(data, dict):
                return self.reply(
                    {"error": "Données invalides"}, 400
                )

            action = urlparse(self.path).path

            # Comptes JusteParler
            if action in (
                "/api/register",
                "/api/login",
                "/api/logout",
                "/api/me"
            ):
                return self.handle_auth(action, data)

            # Appels anonymes existants
            with lock:
                now = time.time()

                for key in list(users):
                    if now - users[key]["seen"] > 35:
                        leave(key)
                        users.pop(key, None)

                if action == "/join":
                    role = data.get("role")

                    if role not in ("talk", "listen"):
                        return self.reply(
                            {"error": "Rôle invalide"}, 400
                        )

                    token = secrets.token_urlsafe(32)

                    users[token] = {
                        "role": role,
                        "peer": None,
                        "queue": [],
                        "seen": now
                    }

                    match()
                    return self.reply({"token": token})

                key = data.get("token")
                user = users.get(key) if isinstance(key, str) else None

                if not user:
                    return self.reply(
                        {"error": "Session expirée"}, 401
                    )

                user["seen"] = now

                if action == "/poll":
                    queue = user["queue"]
                    user["queue"] = []
                    return self.reply({"events": queue})

                if action == "/signal":
                    peer = users.get(user.get("peer"))

                    if (
                        not peer
                        or data.get("room") != user.get("room")
                        or "data" not in data
                    ):
                        return self.reply(
                            {"error": "Signal invalide"}, 400
                        )

                    peer["queue"].append({
                        "type": "signal",
                        "room": user["room"],
                        "data": data["data"]
                    })

                elif action in ("/leave", "/report"):
                    if action == "/report":
                        report = {
                            "time": now,
                            "room": user.get("room"),
                            "reason": str(
                                data.get("reason", "")
                            )[:500]
                        }

                        reports.append(report)

                        with Path("reports.jsonl").open(
                            "a", encoding="utf-8"
                        ) as file:
                            file.write(
                                json.dumps(report) + "\n"
                            )

                    leave(key)
                    users.pop(key, None)

                else:
                    return self.reply(
                        {"error": "Action inconnue"}, 404
                    )

                return self.reply({"ok": True})

        except Exception:
            return self.reply(
                {"error": "Requête invalide"}, 400
            )

    def handle_auth(self, action, data):
        try:
            if action == "/api/register":
                account_id = auth.register(
                    data.get("email", ""),
                    data.get("password", "")
                )

                return self.reply({
                    "ok": True,
                    "account_id": account_id
                }, 201)

            if action == "/api/login":
                token = auth.login(
                    data.get("email", ""),
                    data.get("password", "")
                )

                if not token:
                    return self.reply({
                        "error": "Identifiants invalides"
                    }, 401)

                return self.reply({"token": token})

            token = data.get("token", "")

            if action == "/api/me":
                account = auth.get_account(token)

                if not account:
                    return self.reply({
                        "error": "Session invalide"
                    }, 401)

                return self.reply({"account": account})

            if not isinstance(token, str):
                return self.reply({
                    "error": "Session invalide"
                }, 400)

            auth.logout(token)
            return self.reply({"ok": True})

        except (ValueError, TypeError, AttributeError) as error:
            return self.reply({
                "error": str(error)
            }, 400)

        except Exception:
            return self.reply({
                "error": "Erreur du serveur"
            }, 500)

    def do_GET(self):
        allowed = (
            "/",
            "/index.html",
            "/inscription.html",
            "/manifest.json",
            "/sw.js",
            "/icon.svg"
        )

        if urlparse(self.path).path not in allowed:
            return self.send_error(404)

        super().do_GET()


def leave(key):
    user = users.get(key)

    peer = (
        users.get(user.get("peer"))
        if user else None
    )

    if peer:
        peer["peer"] = None
        peer["role"] = "ended"
        peer["queue"].append({
            "type": "ended"
        })


def match():
    talkers = [
        key for key, user in users.items()
        if user["role"] == "talk"
        and not user["peer"]
    ]

    listeners = [
        key for key, user in users.items()
        if user["role"] == "listen"
        and not user["peer"]
    ]

    for first, second in zip(talkers, listeners):
        room = secrets.token_hex(16)

        for key, peer, offer in (
            (first, second, True),
            (second, first, False)
        ):
            users[key].update(
                peer=peer,
                room=room
            )

            users[key]["queue"].append({
                "type": "match",
                "room": room,
                "offer": offer
            })


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))

    ThreadingHTTPServer(
        ("0.0.0.0", port),
        Handler
    ).serve_forever()
                                                        
