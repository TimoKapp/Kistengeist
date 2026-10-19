"""Datei-Upload übers Netzwerk (Logik ohne Oberfläche, damit sie testbar ist).

Ein kleiner Webserver nimmt Dateien von PC oder Handy entgegen und legt sie im
Upload-Ordner ab. Zugang nur mit einem zufälligen Schlüssel, der im QR-Code bzw.
Link des Upload-Fensters steckt; der Server läuft nur, solange das Fenster offen
ist, und beendet sich nach längerer Untätigkeit selbst.
"""

from __future__ import annotations

import contextlib
import glob
import hmac
import json
import os
import secrets
import shutil
import tempfile
import threading
import time
import unicodedata
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

PORT = 8765
MAX_FILE = 4 * 1024**3  # 4 GB je Datei
RESERVE = 512 * 1024**2  # so viel bleibt auf der Karte immer frei
IDLE_TIMEOUT = 30 * 60  # Sekunden ohne Upload, danach schließt der Zugang
CHUNK = 1024 * 1024
MAX_NAME = 180
MAX_CONNECTIONS = 32  # gleichzeitige Verbindungen; schützt den Pi vor Überlastung
SOCKET_TIMEOUT = 60  # Sekunden ohne Daten, dann wird die Verbindung getrennt

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upload_page.html")

_RESERVED = {"", ".", ".."}


def sanitize_name(raw: str) -> str:
    """Macht aus einem beliebigen Dateinamen einen sicheren Namen ohne Pfadanteile."""
    name = unicodedata.normalize("NFC", raw or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')
    name = name.strip().lstrip(".").strip()
    if len(name.encode()) > MAX_NAME:
        stem, dot, ext = name.rpartition(".")
        if not dot or len(ext) > 10:
            stem, ext = name, ""
        while len((stem + ("." + ext if ext else "")).encode()) > MAX_NAME:
            stem = stem[:-1]
        name = stem + ("." + ext if ext else "")
    return "datei" if name in _RESERVED else name


def unique_path(directory: str, name: str) -> str:
    """Hängt bei Namensgleichheit „ (2)“, „ (3)“ … an."""
    path = os.path.join(directory, name)
    if not os.path.exists(path):
        return path
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    n = 2
    while True:
        candidate = f"{stem} ({n})" + (f".{ext}" if ext else "")
        path = os.path.join(directory, candidate)
        if not os.path.exists(path):
            return path
        n += 1


class UploadServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, directory: str, port: int = PORT, token: str | None = None,
                 on_file: Callable[[str], None] | None = None,
                 on_send: Callable[[str], None] | None = None,
                 idle_timeout: float = IDLE_TIMEOUT, host: str = "") -> None:
        super().__init__((host, port), UploadHandler)
        self.directory = directory
        self.token = token or secrets.token_urlsafe(16)
        self.on_file = on_file
        self.on_send = on_send
        self.idle_timeout = idle_timeout
        self.last_activity = time.monotonic()
        self.received: list[str] = []
        self.lock = threading.Lock()
        self.reserved = 0  # Bytes laufender Uploads (für die Platzprüfung)
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        os.makedirs(directory, exist_ok=True)
        # Reste abgebrochener Uploads (z. B. Fenster während des Uploads geschlossen).
        for stale in glob.glob(os.path.join(directory, ".upload-*.part")):
            with contextlib.suppress(OSError):
                os.unlink(stale)

    def process_request(self, request, client_address) -> None:
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def renew(self) -> None:
        """Neuer Schlüssel und neue Frist (z. B. nach Ablauf)."""
        self.token = secrets.token_urlsafe(16)
        self.touch()

    def free_space(self) -> int:
        """Für Uploads nutzbarer Platz (abzüglich Reserve und laufender Uploads)."""
        with self.lock:
            return max(shutil.disk_usage(self.directory).free - self.reserved - RESERVE, 0)

    def check_token(self, candidate: str | None) -> bool:
        return bool(candidate) and hmac.compare_digest(candidate.encode(), self.token.encode())

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def expired(self) -> bool:
        return time.monotonic() - self.last_activity > self.idle_timeout

    def store(self, raw_name: str, length: int, stream) -> str:
        """Schreibt einen Upload erst in eine .part-Datei und benennt ihn danach um."""
        if length < 0 or length > MAX_FILE:
            raise ValueError("Datei zu groß (höchstens 4 GB).")
        name = sanitize_name(raw_name)
        with self.lock:
            if shutil.disk_usage(self.directory).free - self.reserved - length < RESERVE:
                raise ValueError("Nicht genug Speicherplatz auf dem Pi.")
            self.reserved += length
        part = None
        remaining = length
        try:
            # Versteckte, eindeutige Zwischendatei; der endgültige Name wird erst beim
            # Umbenennen vergeben (so stören sich gleichnamige Uploads nicht).
            fd, part = tempfile.mkstemp(dir=self.directory, prefix=".upload-", suffix=".part")
            os.fchmod(fd, 0o644)
            with os.fdopen(fd, "wb") as fh:
                while remaining:
                    chunk = stream.read(min(CHUNK, remaining))
                    if not chunk:
                        raise ValueError("Upload abgebrochen.")
                    fh.write(chunk)
                    remaining -= len(chunk)
                    self.touch()
            with self.lock:
                target = unique_path(self.directory, name)
                os.replace(part, target)
                self.received.append(target)
        except BaseException:
            if part:
                with contextlib.suppress(OSError):
                    os.unlink(part)
            raise
        finally:
            with self.lock:
                self.reserved -= length
        self.touch()
        if self.on_file:
            self.on_file(target)
        return target


class UploadHandler(BaseHTTPRequestHandler):
    server: UploadServer
    server_version = "KistengeistUpload"
    timeout = SOCKET_TIMEOUT

    def log_message(self, fmt: str, *args) -> None:
        pass

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _query(self) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}

    def _authorized(self) -> bool:
        token = self.headers.get("X-Upload-Token") or self._query().get("t")
        if self.server.expired():
            self._json({"ok": False, "error": "Der Upload-Zugang ist abgelaufen. Am Pi neu öffnen."}, 410)
            return False
        if not self.server.check_token(token):
            self._json({"ok": False, "error": "Ungültiger oder fehlender Zugangsschlüssel."}, 403)
            return False
        self.server.touch()
        return True

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/":
            if not self._authorized():
                return
            try:
                with open(STATIC, "rb") as fh:
                    body = fh.read()
            except OSError:
                self._json({"ok": False, "error": "Seite fehlt."}, 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")  # Schlüssel nicht weitergeben
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/info":
            # Die Seite prüft Größe und Platz vorab: Ablehnungen während eines großen
            # Uploads erreichen den Browser oft nicht (Verbindung wird hart getrennt).
            if not self._authorized():
                return
            self._json({"ok": True, "free": self.server.free_space(), "max_file": MAX_FILE})
        else:
            self._json({"ok": False, "error": "Nicht gefunden."}, 404)

    def do_PUT(self) -> None:  # noqa: N802
        # Bei jeder Ablehnung die Verbindung schließen: der (evtl. große) Body wird nicht gelesen.
        if urlsplit(self.path).path != "/upload":
            self.close_connection = True
            self._json({"ok": False, "error": "Nicht gefunden."}, 404)
            return
        if not self._authorized():
            self.close_connection = True
            return
        raw_name = unquote(self.headers.get("X-File-Name", "")) or self._query().get("name", "")
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0:
            self.close_connection = True
            self._json({"ok": False, "error": "Länge der Datei fehlt."}, 411)
            return
        try:
            target = self.server.store(raw_name, length, self.rfile)
        except ValueError as exc:
            self.close_connection = True
            self._json({"ok": False, "error": str(exc)}, 413 if "groß" in str(exc) or "Speicher" in str(exc) else 400)
            return
        except OSError:
            self.close_connection = True
            self._json({"ok": False, "error": "Speichern fehlgeschlagen (Speicher voll oder Schreibfehler)."}, 507)
            return
        self._json({"ok": True, "name": os.path.basename(target)})
        # Erst antworten, dann Claude öffnen: ein Fehler dort darf den Upload nicht verderben.
        if self.headers.get("X-Send-To-Claude") == "1" and self.server.on_send:
            with contextlib.suppress(Exception):
                self.server.on_send(target)
