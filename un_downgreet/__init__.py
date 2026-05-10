import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pynicotine.config import config
from pynicotine.pluginsystem import BasePlugin


class Plugin(BasePlugin):
    DATA_FILE = "greeted_users.json"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # Runtime paths and state
        self.plugin_dir = Path(__file__).resolve().parent
        self.data_file = self.plugin_dir / self.DATA_FILE
        self._lock = threading.RLock()
        self._users: dict[str, dict[str, Any]] = {}

        # Plugin settings
        defaults = {
            "enabled": True,
            "expiry_days": 180,
            "welcome_message": "Thanks for downloading, {user}.",
            "show_greet_log": True,
        }

        existing = getattr(self, "settings", None)
        self.settings = dict(defaults)

        if isinstance(existing, dict):
            self.settings.update(existing)

        # Settings pane schema
        self.metasettings = {
            "enabled": {
                "description": "Enable Download Greeting",
                "type": "bool",
            },
            "expiry_days": {
                "description": "Username Expiry Days (0 = never expire)",
                "type": "int",
                "minimum": 0,
                "maximum": 5000,
            },
            "welcome_message": {
                "description": "Greeting Message ({user} {expiry_days} {date})",
                "type": "textview",
            },
            "show_greet_log": {
                "description": "Log Greeting Events",
                "type": "bool",
            },
        }

        # Plugin commands
        self.commands = {
            "downgreet": {
                "callback": self.cmd_downgreet,
                "description": "Show greeting record",
            },
            "downgreet_forget": {
                "callback": self.cmd_forget,
                "description": "Forget user",
            },
            "downgreet_clear": {
                "callback": self.cmd_clear,
                "description": "Clear greeting database",
            },
        }

    # Plugin lifecycle
    def init(self) -> None:
        self._sanitize_settings()
        self._load_users()
        self._prune_expired()

    def loaded_notification(self) -> None:
        try:
            self.init()
        except Exception as e:
            self.log(f"Download Greeting init failed: {type(e).__name__}: {e}")

    def settings_changed(self, before: Any, after: Any, change: Any) -> None:
        try:
            self._sanitize_settings()
            self.save_settings()
        except Exception as e:
            self.log(f"Download Greeting settings_changed failed: {type(e).__name__}: {e}")

    # Settings persistence
    def _plugin_key(self) -> str:
        return self.plugin_dir.name

    def _coerce_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return bool(value)

        if isinstance(value, str):
            value = value.strip().lower()

            if value in {"1", "true", "yes", "y", "on", "enabled", "enable"}:
                return True

            if value in {"0", "false", "no", "n", "off", "disabled", "disable"}:
                return False

        return default

    def _coerce_int(self, value: Any, default: int = 0) -> int:
        if isinstance(value, bool):
            return default

        if isinstance(value, int):
            return value

        if isinstance(value, float):
            return int(value)

        if isinstance(value, str):
            try:
                return int(value.strip(), 10)
            except ValueError:
                return default

        return default

    def _clamp_int(self, value: int, minimum: int | None = None, maximum: int | None = None) -> int:
        if minimum is not None:
            value = max(value, int(minimum))

        if maximum is not None:
            value = min(value, int(maximum))

        return value

    def _sanitize_settings(self) -> None:
        with self._lock:
            self.settings["enabled"] = self._coerce_bool(
                self.settings.get("enabled"),
                True,
            )

            self.settings["show_greet_log"] = self._coerce_bool(
                self.settings.get("show_greet_log"),
                True,
            )

            self.settings["expiry_days"] = self._clamp_int(
                self._coerce_int(self.settings.get("expiry_days"), 180),
                0,
                5000,
            )

            message = self.settings.get("welcome_message", "")

            if not isinstance(message, str):
                message = ""

            message = message.strip()

            if not message:
                message = "Thanks for downloading, {user}."

            self.settings["welcome_message"] = message

    def save_settings(self) -> None:
        self._sanitize_settings()

        try:
            plugin_key = self._plugin_key()

            config.sections.setdefault("plugins", {})
            config.sections["plugins"][plugin_key] = dict(self.settings)

            write_fn = (
                getattr(config, "write_configuration", None)
                or getattr(config, "write_config", None)
                or getattr(config, "write", None)
            )

            if not callable(write_fn):
                raise AttributeError("Config object has no write_configuration/write_config/write method")

            write_fn()

        except OSError as e:
            self.log(f"Download Greeting save_settings failed OS error: {e}")
        except Exception as e:
            self.log(f"Download Greeting save_settings failed unexpected: {type(e).__name__}: {e}")

    # JSON storage
    def _load_users(self) -> None:
        with self._lock:
            self._users = {}

            if not self.data_file.exists():
                return

            try:
                data = json.loads(
                    self.data_file.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                )
            except Exception:
                return

            if not isinstance(data, dict):
                return

            users = data.get("users", data)

            if not isinstance(users, dict):
                return

            cleaned: dict[str, dict[str, Any]] = {}

            for user, info in users.items():
                if not isinstance(user, str):
                    continue

                user = user.strip()

                if not user or not isinstance(info, dict):
                    continue

                try:
                    count = int(info.get("count", 0) or 0)
                except Exception:
                    count = 0

                cleaned[user] = {
                    "first": str(info.get("first", "") or ""),
                    "last": str(info.get("last", "") or ""),
                    "last_greeted": str(info.get("last_greeted", "") or ""),
                    "expiry": str(info.get("expiry", "") or ""),
                    "count": max(0, count),
                }

            self._users = cleaned

    def _save_users(self) -> None:
        with self._lock:
            payload = {"users": self._users}
            tmp = self.data_file.with_suffix(".json.tmp")

            try:
                tmp.write_text(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    encoding="utf-8",
                )

                tmp.replace(self.data_file)

            except Exception as e:
                self.log(f"Download Greeting save failed: {type(e).__name__}: {e}")

    # Time helpers
    def _iso_now(self) -> str:
        return datetime.now().replace(microsecond=0).isoformat()

    def _iso_expiry(self) -> str:
        days = int(self.settings.get("expiry_days", 180))

        if days <= 0:
            return ""

        return (datetime.now() + timedelta(days=days)).replace(microsecond=0).isoformat()

    def _expired(self, expiry: str) -> bool:
        if not expiry:
            return False

        try:
            return datetime.fromisoformat(expiry) <= datetime.now()
        except Exception:
            return True

    def _prune_expired(self) -> None:
        with self._lock:
            before = len(self._users)

            self._users = {
                user: info
                for user, info in self._users.items()
                if not self._expired(str(info.get("expiry", "") or ""))
            }

            changed = len(self._users) != before

        if changed:
            self._save_users()

    # Greeting logic
    def _format_message(self, user: str) -> str:
        expiry_days = int(self.settings.get("expiry_days", 180))
        today = datetime.now().strftime("%Y-%m-%d")

        return (
            self.settings.get("welcome_message", "")
            .replace("{user}", user)
            .replace("{expiry_days}", str(expiry_days))
            .replace("{date}", today)
        )

    def _send_greeting(self, user: str) -> bool:
        try:
            self.send_private(user, self._format_message(user))
            return True

        except Exception as e:
            self.log(f"Download Greeting PM failed for {user}: {type(e).__name__}: {e}")
            return False

    def _should_greet(self, user: str) -> bool:
        with self._lock:
            info = self._users.get(user)

        if not info:
            return True

        return self._expired(str(info.get("expiry", "") or ""))

    def _remember_user(self, user: str, greeted: bool = False) -> None:
        now = self._iso_now()

        with self._lock:
            old = self._users.get(user, {})
            first = old.get("first") or now
            last_greeted = now if greeted else old.get("last_greeted", "")

            try:
                count = int(old.get("count", 0) or 0)
            except Exception:
                count = 0

            self._users[user] = {
                "first": first,
                "last": now,
                "last_greeted": last_greeted,
                "expiry": self._iso_expiry(),
                "count": count + 1,
            }

        self._save_users()

    # Queue event
    def upload_queued_notification(self, user: str, filename: str, file_id: Any) -> None:
        if not self.settings.get("enabled", True):
            return

        user = (user or "").strip()

        if not user:
            return

        greet = self._should_greet(user)
        sent = False

        if greet:
            sent = self._send_greeting(user)

            if sent and self.settings.get("show_greet_log", True):
                self.log(f"{user} greeted")

        self._remember_user(user, greeted=sent)

    # Commands
    def cmd_downgreet(self, arg: str = "", **_: Any) -> None:
        user = (arg or "").strip()

        if not user:
            self.output("Usage: /downgreet <user>")
            return

        with self._lock:
            info = self._users.get(user)

        if not info:
            self.output(f"No greeting record for {user}")
            return

        self.output(
            f"{user}: "
            f"first={info.get('first', '')}, "
            f"last={info.get('last', '')}, "
            f"last_greeted={info.get('last_greeted', '') or 'never'}, "
            f"expiry={info.get('expiry', '') or 'never'}, "
            f"downloads={info.get('count', 0)}"
        )

    def cmd_forget(self, arg: str = "", **_: Any) -> None:
        user = (arg or "").strip()

        if not user:
            self.output("Usage: /downgreet_forget <user>")
            return

        with self._lock:
            if user not in self._users:
                self.output(f"No greeting record for {user}")
                return

            self._users.pop(user, None)

        self._save_users()
        self.output(f"Forgot {user}")

    def cmd_clear(self, *_: Any, **__: Any) -> None:
        with self._lock:
            self._users.clear()

        self._save_users()
        self.output("Greeting database cleared")