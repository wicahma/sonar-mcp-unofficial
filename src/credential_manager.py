from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import webbrowser

from client import SonarClient, SonarError


ENV_KEYS = {
    "base_url": "SONAR_HOST_URL",
    "token": "SONAR_TOKEN",
    "token_file": "SONAR_TOKEN_FILE",
}


def credentials_path() -> str:
    return os.environ.get("SONAR_CREDENTIALS_PATH") or os.path.expanduser(
        r"~/.omp/sonar_credentials.json"
    )


def load_credentials() -> dict:
    credentials: dict = {}
    path = credentials_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                credentials.update({k: v for k, v in stored.items() if isinstance(v, str)})
        except (OSError, ValueError) as exc:
            sys.stderr.write(f"Warning: failed reading SonarQube credentials file: {exc}\n")

    for key, env_name in ENV_KEYS.items():
        value = os.environ.get(env_name)
        if value is not None and value.strip():
            credentials[key] = value

    return credentials


def build_client(**overrides) -> SonarClient:
    credentials = load_credentials()
    credentials.update({k: v for k, v in overrides.items() if v is not None})
    return SonarClient(
        credentials.get("base_url"),
        token=credentials.get("token"),
        token_file=credentials.get("token_file"),
    )


def verify(client: SonarClient) -> bool:
    if not client.base_url:
        print("[AUTH_FAILED] Base URL SonarQube belum diisi (--base-url / SONAR_HOST_URL / file kredensial).")
        return False
    try:
        result = client.request("GET", "/api/authentication/validate")
        if isinstance(result, dict) and result.get("valid") is False:
            raise SonarError(0, "Token ditolak oleh /api/authentication/validate")
        user = client.request("GET", "/api/users/current")
        print(f"[AUTH_OK] Login berhasil sebagai: {user.get('name')} ({user.get('login')})")
        return True
    except (SonarError, ValueError, OSError) as exc:
        print(f"[AUTH_FAILED] {exc}")
        return False


def save_credentials(data: dict) -> str:
    path = credentials_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f"Kredensial SonarQube disimpan di {path}")
    return path


def cmd_check(args: argparse.Namespace) -> int:
    return 0 if verify(build_client()) else 1


def cmd_update(args: argparse.Namespace) -> int:
    data = load_credentials()
    data["base_url"] = (args.base_url or data.get("base_url") or "").strip()
    if not data["base_url"]:
        print("SonarQube base URL wajib: berikan --base-url, SONAR_HOST_URL, atau file kredensial.")
        return 1

    token = (args.token or "").strip() or data.get("token")
    token_file = (args.token_file or "").strip() or data.get("token_file")
    if not token and not token_file:
        token = getpass.getpass("SonarQube USER token: ").strip()
    if token:
        data["token"] = token
    if token_file:
        data["token_file"] = token_file

    client = SonarClient(data["base_url"], token=data.get("token"), token_file=data.get("token_file"))
    if not verify(client):
        print("Kredensial tidak diverifikasi; tidak ada yang disimpan.")
        return 1
    save_credentials(data)
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    base_url = (args.base_url or "").strip().rstrip("/")
    if not base_url:
        print("login membutuhkan --base-url (URL web SonarQube, mis. https://techno-sonar.berijalan.id).")
        return 1
    if args.credentials_path:
        os.environ["SONAR_CREDENTIALS_PATH"] = args.credentials_path

    print(f"Membuka browser ke {base_url} ...")
    try:
        webbrowser.open(base_url)
    except Exception as exc:  # webbrowser gagal beberapa platform; instruksi tetap tampil
        print(f"Browser tidak bisa dibuka otomatis ({exc}). Buka manual URL tersebut.")

    print(
        "\nLogin via GitLab terjadi di browser (OAuth menghasilkan sesi browser, bukan token Web API).\n"
        "Setelah login, buka: My Account -> Security -> Generate Tokens\n"
        "Buat token dengan tipe USER (bukan project token), lalu tempel di bawah ini."
    )
    token = getpass.getpass("SonarQube USER token: ").strip()
    if not token:
        print("Token kosong; tidak ada yang disimpan.")
        return 1

    data = dict(load_credentials())
    data["base_url"] = base_url
    data["token"] = token
    client = SonarClient(base_url, token=token)
    if not verify(client):
        print("Kredensial tidak diverifikasi; tidak ada yang disimpan.")
        return 1
    save_credentials(data)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Kelola kredensial SonarQube untuk MCP ini.")
    parser.add_argument("action", choices=["login", "update", "check"])
    parser.add_argument("--base-url", help="URL SonarQube (mis. https://techno-sonar.berijalan.id)")
    parser.add_argument("--token", help="USER token SonarQube")
    parser.add_argument("--token-file", help="Path file yang berisi USER token SonarQube")
    parser.add_argument("--credentials-path", help="Path file kredensial JSON untuk login")
    args = parser.parse_args()

    if args.action == "check":
        return cmd_check(args)
    if args.action == "login":
        return cmd_login(args)
    return cmd_update(args)


if __name__ == "__main__":
    sys.exit(main())
