import os
import sqlite3
import hmac
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash, session
import paramiko
from werkzeug.security import check_password_hash


LOGIN_USERNAME = os.environ.get("APP_LOGIN_USER", "admin")
LOGIN_PASSWORD = os.environ.get("APP_LOGIN_PASSWORD", "admin")
LOGIN_PASSWORD_HASH = os.environ.get("APP_LOGIN_PASSWORD_HASH")
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(Path(__file__).resolve().parent / "ssh_dashboard.sqlite3")))
DEFAULT_ALLOWED_COMMANDS = "uname -a,uptime,whoami,df -h,free -m"


def verify_password(provided_password: str) -> bool:
    if LOGIN_PASSWORD_HASH:
        return check_password_hash(LOGIN_PASSWORD_HASH, provided_password)
    return hmac.compare_digest(provided_password, LOGIN_PASSWORD)


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS command_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                host TEXT NOT NULL,
                username TEXT NOT NULL,
                command TEXT NOT NULL,
                stdout TEXT NOT NULL DEFAULT '',
                stderr TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL
            )
            """
        )
        conn.commit()


def fetch_command_log(limit: int = 50) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT timestamp, host, username, command, stdout, stderr, status
            FROM command_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def save_command_log(entry: dict) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO command_log (timestamp, host, username, command, stdout, stderr, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["timestamp"],
                entry["host"],
                entry["username"],
                entry["command"],
                entry["stdout"],
                entry["stderr"],
                entry["status"],
            ),
        )
        conn.commit()


def get_allowed_commands() -> list[str]:
    raw = os.environ.get("ALLOWED_COMMANDS", DEFAULT_ALLOWED_COMMANDS)
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_allowed_hosts() -> set[str]:
    raw = os.environ.get("ALLOWED_SSH_HOSTS", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def sanitize_command(command: str) -> str:
    cleaned = command.strip()
    if not cleaned:
        raise ValueError("Comanda este goală.")

    unsafe_tokens = (";", "&&", "||", "|", "`", "$(", "\n", "\r")
    if any(token in cleaned for token in unsafe_tokens):
        raise ValueError("Comanda conține simboluri periculoase.")

    allowed = get_allowed_commands()
    if allowed and cleaned not in allowed:
        raise ValueError("Comanda nu este permisă de configurația aplicației.")

    return cleaned


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapped


def create_app() -> Flask:
    init_db()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or os.urandom(32).hex(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not app.debug,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            user = request.form.get("username", "").strip()
            pwd = request.form.get("password", "")
            if user == LOGIN_USERNAME and verify_password(pwd):
                session.clear()
                session["logged_in"] = True
                session["username"] = user
                return redirect(url_for("commands"))
            flash("Utilizator sau parolă incorectă.", "error")
            return redirect(url_for("login"))

        if session.get("logged_in"):
            return redirect(url_for("commands"))
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def index():
        return redirect(url_for("commands"))

    @app.route("/commands", methods=["GET", "POST"])
    @login_required
    def commands():
        if request.method == "POST":
            host = request.form.get("host", "").strip()
            port_raw = request.form.get("port", "22").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            command = request.form.get("command", "").strip()

            if not host or not username or not password or not command:
                flash("Toate câmpurile sunt obligatorii.", "error")
                return redirect(url_for("commands"))

            allowed_hosts = get_allowed_hosts()
            if allowed_hosts and host.lower() not in allowed_hosts:
                flash("Host-ul nu este permis de configurația aplicației.", "error")
                return redirect(url_for("commands"))

            try:
                port = int(port_raw)
                if not 1 <= port <= 65535:
                    raise ValueError
            except ValueError:
                flash("Port invalid.", "error")
                return redirect(url_for("commands"))

            try:
                command = sanitize_command(command)
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for("commands"))

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = {
                "timestamp": timestamp,
                "host": host,
                "username": username,
                "command": command,
                "stdout": "",
                "stderr": "",
                "status": "pending",
            }

            try:
                ssh = paramiko.SSHClient()
                known_hosts_file = os.environ.get("SSH_KNOWN_HOSTS_FILE")
                if known_hosts_file:
                    ssh.load_system_host_keys(known_hosts_file)
                ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
                ssh.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    look_for_keys=False,
                    allow_agent=False,
                    timeout=10,
                )

                stdin, stdout, stderr = ssh.exec_command(command)
                _ = stdin
                out_text = stdout.read().decode("utf-8", errors="replace")
                err_text = stderr.read().decode("utf-8", errors="replace")
                exit_status = stdout.channel.recv_exit_status()
                ssh.close()

                entry["stdout"] = out_text
                entry["stderr"] = err_text
                entry["status"] = "success" if exit_status == 0 else f"exit {exit_status}"
            except Exception as exc:  # noqa: BLE001
                entry["stderr"] = str(exc)
                entry["status"] = "error"

            save_command_log(entry)
            return redirect(url_for("commands"))

        return render_template(
            "commands.html",
            command_log=fetch_command_log(50),
            active_menu="commands",
        )

    @app.route("/settings")
    @login_required
    def settings():
        return render_template("settings.html", active_menu="settings")

    @app.route("/users")
    @login_required
    def users():
        return render_template("users.html", active_menu="users")

    @app.context_processor
    def inject_vendor():
        """Folosește resurse locale când USE_LOCAL_VENDOR=1 (ex. în Docker offline)."""
        use_local = os.environ.get("USE_LOCAL_VENDOR", "0") == "1"
        return {"use_local_vendor": use_local}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
