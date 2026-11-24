# sonar-mcp-unofficial

Connector MCP buatan sendiri untuk SonarQube privat. Fokusnya sempit: ambil detail issue
(lokasi, alasan, cara perbaiki), ringkasan kualitas, dan security hotspot—plus update status
(terutama false positive). Seluruh tool dibangun di atas `httpx` + FastMCP dan berbicara
langsung ke SonarQube Web API; tidak membungkus biner MCP orang lain.

URL instance tidak disimpan di repo; ditentukan lewat `SONAR_HOST_URL` atau file kredensial lokal.

## Instalasi

```bash
pip install -r requirements.txt
```

Python 3.12+, `mcp>=1.29,<2`, `httpx>=0.28,<1`.

## Kenapa login pakai helper browser, bukan OAuth langsung

Tombol **Log in with GitLab** di web Sonar menjalankan OAuth 2.0 yang menghasilkan **sesi browser**
(cookie), bukan token Web API. Sesi itu hidup di browser dan tidak bisa dibaca oleh server stdio.
Spesifikasi MCP juga menetapkan kredensial transport stdio diambil dari environment/file;
OAuth 2.1 hanya untuk transport HTTP. Karena itu alurnya:

1. `login` membuka browser ke URL Sonar; user login dengan GitLab di browser.
2. Di web Sonar, buka **My Account → Security → Generate Tokens**, buat token bertipe **User**.
3. Tempel token ke prompt CLI; server memverifikasi lewat `/api/authentication/validate` dan
   `/api/users/current`, lalu menyimpannya lokal. Token tidak pernah dicetak.

Tidak ada automasi OAuth/cookie/XSRF, dan tidak memakai `api/user_tokens/generate` (endpoint internal
yang butuh sesi). Helper ini sengaja hanya membuka browser dan menerima token dari user.

```bash
python src/credential_manager.py login \
  --base-url https://techno-sonar.berijalan.id \
  --credentials-path D:\User\.omp\sonar_credentials.json
python src/credential_manager.py check
```

Rotasi manual tanpa browser:

```bash
python src/credential_manager.py update --base-url https://techno-sonar.berijalan.id --token <USER_TOKEN>
python src/credential_manager.py update --token-file /path/ke/token.txt
```

`update`/`login` menyimpan JSON ke `SONAR_CREDENTIALS_PATH` (default `~/.omp/sonar_credentials.json`)
dengan izin `0600` (best-effort) dan memverifikasi dulu. Gagal verifikasi → tidak ada yang disimpan.

> **Wajib USER token, bukan project token.** SonarQube menolak project token untuk Web API.
> Tool update membutuhkan permission **Administer Issues** dan **Administer Security Hotspot**
> pada token tersebut; tanpa itu Sonar mengembalikan 403 dan error diteruskan apa adanya.

### Environment variable

| Nama | Fungsi |
| --- | --- |
| `SONAR_HOST_URL` | Base URL SonarQube (wajib, atau lewat file kredensial) |
| `SONAR_TOKEN` | USER token SonarQube |
| `SONAR_TOKEN_FILE` | Path file token; dibaca ulang tiap request agar rotasi langsung aktif |
| `SONAR_CREDENTIALS_PATH` | Path file kredensial JSON (default `~/.omp/sonar_credentials.json`) |
| `SONAR_MCP_TRANSPORT` | `stdio` (default) atau `streamable-http` |

Prioritas: `SONAR_TOKEN` → isi `SONAR_TOKEN_FILE` → nilai di file kredensial.

## Konfigurasi MCP (agent lain)

Server ini hanya memakai `command`/`args`/`env` standar, jadi bisa dipakai Claude Code, Cursor,
Gemini CLI, atau agent lain yang mendukung MCP stdio:

```json
"sonar": {
  "command": "python",
  "args": ["D:\\Berijalan\\repo\\sonar-mcp-unofficial\\src\\runner.py"],
  "env": {
    "SONAR_CREDENTIALS_PATH": "D:\\User\\.omp\\sonar_credentials.json"
  }
}
```

Manual:

```bash
python src/runner.py --transport stdio
python src/runner.py --transport streamable-http --host 127.0.0.1 --port 8124
```

## Tool

| Grup | Tool | Fungsi |
| --- | --- | --- |
| Inti | `sonar_health`, `sonar_whoami` | Versi server, identitas token |
| Inti | `sonar_search_projects` | Cari project key (jangan menebak key) |
| Issue | `sonar_list_issues` | Daftar issue ringkas + filter project/branch/status/new code |
| Issue | `sonar_get_issue_detail` | Lokasi, `why`, `how_to_fix`, alur, transisi, aturan |
| Issue | `sonar_get_issue_summary` | Agregat facet + jumlah hotspot |
| Issue | `sonar_update_issue_status` | Transisi issue + komentar (wajib `confirm=True`) |
| Hotspot | `sonar_list_hotspots` | Daftar security hotspot |
| Hotspot | `sonar_get_hotspot_detail` | Rule, `why`, `how_to_fix` hotspot |
| Hotspot | `sonar_update_hotspot_status` | Ubah status/resolusi (wajib `confirm=True`) |

Semua tool bersifat read-only kecuali dua tool update; keduanya menolak eksekusi tanpa
`confirm=True`. Tidak ada tool passthrough umum—ini mencegah write di luar tool yang disengaja.
Saat memakai tool dari agent, cari project key dulu dengan `sonar_search_projects` dan sertakan
`branch` bila issue berada di feature branch.

## Verifikasi

```bash
python src/credential_manager.py check
python src/doctor.py
python -m unittest discover -s tests -v
```

`doctor.py` melakukan probe read-only ke `/api/server/version`, `/api/authentication/validate`,
`/api/users/current`, dan `/api/projects/search?ps=1`, lalu mencetak ringkasan JSON tanpa token.
Unit test memakai fixture offline—tidak ada network call.
