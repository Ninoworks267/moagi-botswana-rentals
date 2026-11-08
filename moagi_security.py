
import requests
from urllib.parse import urljoin

print("""
========================================
          MOAGI SECURITY AUDIT
========================================
""")

BASE_URL = input("Enter MOAGI URL (e.g. http://127.0.0.1:5000): ").strip().rstrip("/")

if not BASE_URL.startswith(("http://", "https://")):
    BASE_URL = "http://" + BASE_URL

s = requests.Session()
s.headers["User-Agent"] = "MOAGI-Authorized-Security-Audit/1.0"

passed = 0
warnings = 0

def report(name, ok, detail=""):
    global passed, warnings
    if ok:
        passed += 1
        print("[PASS] " + name)
    else:
        warnings += 1
        print("[CHECK] " + name)
    if detail:
        print("       " + str(detail))

def test_file(path):
    try:
        r = s.get(urljoin(BASE_URL + "/", path), timeout=5)
        if r.status_code == 404 or r.status_code == 403:
            report(path, True, "Not publicly accessible")
        elif r.status_code == 200:
            report(path, False, "Returned HTTP 200; inspect manually")
        else:
            report(path, True, "HTTP " + str(r.status_code))
    except requests.RequestException:
        report(path, False, "Request failed")

try:
    print("\nConnecting to MOAGI...")
    r = s.get(BASE_URL, timeout=10)

    print("Website status:", r.status_code)

    print("\n--- SECURITY HEADERS ---")

    headers = r.headers

    for h in [
        "Content-Security-Policy",
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy"
    ]:
        report(h, h in headers, headers.get(h, "Missing"))

    print("\n--- HTTPS ---")
    report("HTTPS enabled", r.url.startswith("https://"), r.url)

    print("\n--- COOKIE SECURITY ---")

    cookies = r.headers.get("Set-Cookie", "").lower()

    if cookies:
        report("HttpOnly", "httponly" in cookies)
        report("Secure", "secure" in cookies)
        report("SameSite", "samesite" in cookies)
    else:
        print("No cookies issued on homepage.")

    print("\n--- SENSITIVE FILES ---")

    for path in [
        ".env",
        ".git/config",
        "moagi.db",
        "database.db",
        "backup.zip",
        "config.py"
    ]:
        test_file(path)

    print("\n--- PRIVATE PAGE ACCESS ---")

    for path in [
        "inbox",
        "messages",
        "profile",
        "dashboard",
        "landlord/dashboard",
        "tenant/dashboard"
    ]:
        try:
            p = s.get(
                urljoin(BASE_URL + "/", path),
                timeout=5,
                allow_redirects=False
            )

            protected = (
                p.status_code in (401, 403)
                or (
                    p.status_code in (301, 302, 303, 307, 308)
                    and "login" in p.headers.get("Location", "").lower()
                )
            )

            report(
                path,
                protected,
                "HTTP " + str(p.status_code)
            )
        except requests.RequestException:
            report(path, False, "Request failed")

    print("\n========================================")
    print("             AUDIT RESULTS")
    print("========================================")
    print("Passed:", passed)
    print("Needs checking:", warnings)
    print("\nThis is a preliminary audit, not a")
    print("complete penetration test.")

except requests.RequestException as e:
    print("\nConnection failed:", e)
    print("Check that MOAGI is running.")

input("\nPress ENTER to close...")
