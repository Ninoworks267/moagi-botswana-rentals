
import os
import sqlite3
from getpass import getpass
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "moagi.db")

print("MOAGI ADMIN ACCOUNT SETUP")
print("-------------------------")

first = input("Admin first name: ").strip()
last = input("Admin surname: ").strip()
email = input("Admin email: ").strip().lower()
phone = input("Admin phone: ").strip()

password = getpass("Choose admin password (minimum 12 characters): ")
confirm = getpass("Confirm admin password: ")

if not all([first, last, email, phone]):
    raise SystemExit("All account details are required.")

if len(password) < 12:
    raise SystemExit("Password must contain at least 12 characters.")

if password != confirm:
    raise SystemExit("Passwords do not match.")

conn = sqlite3.connect(DB_PATH)

try:
    existing = conn.execute(
        "SELECT id FROM users WHERE lower(email)=lower(?)",
        (email,)
    ).fetchone()

    if existing:
        raise SystemExit(
            "That email already belongs to an account. "
            "No existing account was changed."
        )

    conn.execute("""
        INSERT INTO users
        (first_name, surname, email, phone, password,
         role, citizenship, location, bio)
        VALUES (?, ?, ?, ?, ?, 'admin', 'Botswana',
                'Gaborone', 'MOAGI platform administrator')
    """, (
        first,
        last,
        email,
        phone,
        generate_password_hash(password)
    ))

    conn.commit()
    print("\nSUCCESS! MOAGI administrator account created.")

except Exception:
    conn.rollback()
    raise

finally:
    conn.close()
