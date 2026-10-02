"""Reset password admin (jalankan lewat reset_admin_password.bat atau manual)."""
from getpass import getpass

from werkzeug.security import generate_password_hash

import db


def main():
    pwd = getpass("Password admin baru (min. 6 karakter): ")
    if len(pwd) < 6:
        raise SystemExit("❌ Password terlalu pendek (minimal 6 karakter).")
    with db.get_conn() as c:
        c.execute("UPDATE admin SET password_hash = ?",
                  (generate_password_hash(pwd),))
    print("✅ Password admin berhasil diganti. Login ulang dengan password baru.")


if __name__ == "__main__":
    main()
