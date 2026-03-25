from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import os
import traceback
import requests
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ------------------ OSNOVNE NASTAVITVE ------------------
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")

print("=== ZAGON APLIKACIJE ===")
print("SENDGRID_API_KEY exists:", bool(SENDGRID_API_KEY))
print("MAIL_DEFAULT_SENDER:", app.config["MAIL_DEFAULT_SENDER"])
print("ADMIN_EMAIL:", ADMIN_EMAIL)

# ------------------ DNEVI ------------------
DNEVI = {
    0: "Ponedeljek",
    1: "Torek",
    2: "Sreda",
    3: "Četrtek",
    4: "Petek",
    5: "Sobota",
    6: "Nedelja"
}

# ------------------ DATABASE ------------------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        phone TEXT,
        role TEXT NOT NULL DEFAULT 'user'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS terms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        hairstyle TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'free',
        user_email TEXT DEFAULT '',
        UNIQUE(date, time)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS closed_days (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT UNIQUE
    )
    """)

    db.commit()
    db.close()


def migrate_db():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("PRAGMA table_info(users)")
    columns = [col["name"] for col in cursor.fetchall()]

    if "phone" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        db.commit()
        print("Phone stolpec dodan.")
    else:
        print("Phone stolpec že obstaja.")

    db.close()


init_db()
migrate_db()

# ------------------ BRISANJE POTEKLIH TERMINOV ------------------
def pobrisi_potekle_termine():
    db = get_db()
    cursor = db.cursor()

    zdaj = datetime.now()
    danes = zdaj.strftime("%Y-%m-%d")
    trenutna_ura = zdaj.strftime("%H:%M")

    cursor.execute("DELETE FROM terms WHERE date < ?", (danes,))
    cursor.execute("DELETE FROM terms WHERE date = ? AND time < ?", (danes, trenutna_ura))

    db.commit()
    db.close()


@app.before_request
def pred_vsako_zahtevo():
    pobrisi_potekle_termine()

# ------------------ PRIPRAVA DNI ZA PRIKAZ ------------------
def pripravi_dneve_za_prikaz(termini, stevilo_dni=14):
    po_dnevih = {}

    for termin in termini:
        termin_id = termin["id"]
        datum = termin["date"]
        ura = termin["time"]
        frizura = termin["hairstyle"]
        status = termin["status"]
        user_email = termin["user_email"]

        datum_obj = datetime.strptime(datum, "%Y-%m-%d")
        ime_dneva = DNEVI[datum_obj.weekday()]

        if datum not in po_dnevih:
            po_dnevih[datum] = {
                "datum": datum,
                "ime_dneva": ime_dneva,
                "termini": []
            }

        po_dnevih[datum]["termini"].append({
            "id": termin_id,
            "date": datum,
            "time": ura,
            "hairstyle": frizura,
            "status": status,
            "user_email": user_email
        })

    danes = datetime.today()
    zacetek = danes - timedelta(days=danes.weekday())

    rezultat = []

    for i in range(stevilo_dni):
        dan_obj = zacetek + timedelta(days=i)
        datum = dan_obj.strftime("%Y-%m-%d")
        ime_dneva = DNEVI[dan_obj.weekday()]

        if datum in po_dnevih:
            rezultat.append(po_dnevih[datum])
        else:
            rezultat.append({
                "datum": datum,
                "ime_dneva": ime_dneva,
                "termini": []
            })

    return rezultat

# ------------------ USTVARI DNEVE ------------------
def ustvari_dneve(zacetek_dneva, stevilo_dni):
    db = get_db()
    cursor = db.cursor()

    ure = ["12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00"]

    for i in range(stevilo_dni):
        dan = zacetek_dneva + timedelta(days=i)
        datum = dan.strftime("%Y-%m-%d")

        for ura in ure:
            cursor.execute("SELECT id FROM terms WHERE date=? AND time=?", (datum, ura))
            obstaja = cursor.fetchone()

            if not obstaja:
                cursor.execute("""
                    INSERT INTO terms (date, time, hairstyle, status, user_email)
                    VALUES (?, ?, '', 'free', '')
                """, (datum, ura))

    db.commit()
    db.close()

# ------------------ EMAIL HELPERS ------------------
def mail_settings_ready():
    missing = []

    if not SENDGRID_API_KEY:
        missing.append("SENDGRID_API_KEY")
    if not app.config["MAIL_DEFAULT_SENDER"]:
        missing.append("MAIL_DEFAULT_SENDER")
    if not ADMIN_EMAIL:
        missing.append("ADMIN_EMAIL")

    if missing:
        print("Manjkajoče mail nastavitve:", ", ".join(missing))
        return False

    return True


def send_sendgrid_email(to_email, subject, plain_body, html_body):
    url = "https://api.sendgrid.com/v3/mail/send"

    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "personalizations": [
            {
                "to": [{"email": to_email}]
            }
        ],
        "from": {
            "email": app.config["MAIL_DEFAULT_SENDER"],
            "name": "Budi Blendz"
        },
        "subject": subject,
        "content": [
            {
                "type": "text/plain",
                "value": plain_body
            },
            {
                "type": "text/html",
                "value": html_body
            }
        ]
    }

    response = requests.post(url, headers=headers, json=payload, timeout=15)

    print("SendGrid status:", response.status_code)
    if response.text:
        print("SendGrid response:", response.text)

    response.raise_for_status()


def send_booking_emails(user_email, user_name, user_phone, term_date, term_time, hairstyle):
    print("FUNKCIJA ZA EMAIL SE JE ZAGNALA")

    if not mail_settings_ready():
        print("Email ni bil poslan, ker nastavitve niso popolne.")
        return False

    user_plain = f"""Pozdravljen {user_name},

tvoj termin je uspešno rezerviran.

Datum: {term_date}
Ura: {term_time}
Storitev: {hairstyle}
Telefon: {user_phone}

Hvala za rezervacijo.
Budi Blendz
"""

    user_html = f"""
    <div style="margin:0;padding:40px 20px;background:#f3f3f3;font-family:Arial,sans-serif;">
        <div style="max-width:620px;margin:0 auto;background:#f7f5ef;border-radius:20px;overflow:hidden;box-shadow:0 12px 30px rgba(0,0,0,0.08);">
            
            <div style="background:linear-gradient(135deg,#0d0d0d,#1b1b1b);padding:34px 24px;text-align:center;">
                <div style="width:130px;height:130px;margin:0 auto 18px auto;background:#f4f1ed;border-radius:14px;display:flex;align-items:center;justify-content:center;border:6px solid #ffffff;padding:10px;box-sizing:border-box;">
                    <img src="https://budi-blendz-zaklucna.onrender.com/static/images/logo.jpg"
                         alt="Budi Blendz logo"
                         style="max-width:100%;max-height:100%;display:block;border-radius:8px;">
                </div>
                <div style="color:#caa84a;font-size:13px;letter-spacing:4px;text-transform:uppercase;margin-bottom:14px;">
                    Potrditev rezervacije
                </div>
                <h1 style="margin:0;color:#ffffff;font-size:34px;font-weight:800;">
                    Uspešna rezervacija
                </h1>
                <p style="margin:12px 0 0 0;color:#dddddd;font-size:14px;">
                    Budi Blendz sistemsko obvestilo
                </p>
            </div>

            <div style="padding:34px 26px 24px 26px;color:#222;">
                <p style="margin-top:0;font-size:17px;line-height:1.7;">
                    Pozdravljen <strong>{user_name}</strong>,
                </p>

                <p style="font-size:15px;line-height:1.7;color:#555;">
                    tvoj termin je uspešno rezerviran.
                </p>

                <div style="margin:28px 0;padding:22px;background:#efede8;border:1px solid #d7b85a;border-radius:16px;">
                    <table style="width:100%;border-collapse:collapse;">
                        <tr>
                            <td style="padding:12px 0;color:#777;font-size:14px;">Datum</td>
                            <td style="padding:12px 0;color:#111;font-size:14px;font-weight:bold;text-align:right;">{term_date}</td>
                        </tr>
                        <tr>
                            <td style="padding:12px 0;color:#777;font-size:14px;">Ura</td>
                            <td style="padding:12px 0;color:#111;font-size:14px;font-weight:bold;text-align:right;">{term_time}</td>
                        </tr>
                        <tr>
                            <td style="padding:12px 0;color:#777;font-size:14px;">Storitev</td>
                            <td style="padding:12px 0;color:#111;font-size:14px;font-weight:bold;text-align:right;">{hairstyle}</td>
                        </tr>
                        <tr>
                            <td style="padding:12px 0;color:#777;font-size:14px;">Telefon</td>
                            <td style="padding:12px 0;color:#111;font-size:14px;font-weight:bold;text-align:right;">{user_phone}</td>
                        </tr>
                    </table>
                </div>

                <p style="font-size:14px;line-height:1.7;color:#666;margin-bottom:0;">
                    Hvala za rezervacijo.<br>
                    <strong>Budi Blendz</strong>
                </p>
            </div>

            <div style="padding:18px 20px;text-align:center;background:#ece8df;color:#8b8b8b;font-size:12px;">
                Budi Blendz • Samodejno sistemsko obvestilo
            </div>
        </div>
    </div>
    """

    admin_plain = f"""Nova rezervacija termina

Ime: {user_name}
Email: {user_email}
Telefon: {user_phone}
Datum: {term_date}
Ura: {term_time}
Storitev: {hairstyle}
"""

    admin_html = f"""
    <div style="margin:0;padding:40px 20px;background:#f3f3f3;font-family:Arial,sans-serif;">
        <div style="max-width:620px;margin:0 auto;background:#f7f5ef;border-radius:20px;overflow:hidden;box-shadow:0 12px 30px rgba(0,0,0,0.08);">
            
            <div style="background:linear-gradient(135deg,#0d0d0d,#1b1b1b);padding:34px 24px;text-align:center;">
                <div style="width:130px;height:130px;margin:0 auto 18px auto;background:#f4f1ed;border-radius:14px;display:flex;align-items:center;justify-content:center;border:6px solid #ffffff;padding:10px;box-sizing:border-box;">
                    <img src="https://budi-blendz-zaklucna.onrender.com/static/images/logo.jpg"
                         alt="Budi Blendz logo"
                         style="max-width:100%;max-height:100%;display:block;border-radius:8px;">
                </div>
                <div style="color:#caa84a;font-size:13px;letter-spacing:4px;text-transform:uppercase;margin-bottom:14px;">
                    Admin Notification
                </div>
                <h1 style="margin:0;color:#ffffff;font-size:34px;font-weight:800;">
                    Nova rezervacija
                </h1>
                <p style="margin:12px 0 0 0;color:#dddddd;font-size:14px;">
                    Budi Blendz sistemsko obvestilo
                </p>
            </div>

            <div style="padding:34px 26px 24px 26px;color:#222;">
                <p style="margin-top:0;font-size:16px;line-height:1.7;">
                    Rezerviran je nov termin.
                </p>

                <div style="margin:28px 0;padding:22px;background:#efede8;border:1px solid #d7b85a;border-radius:16px;">
                    <table style="width:100%;border-collapse:collapse;">
                        <tr>
                            <td style="padding:12px 0;color:#777;font-size:14px;">Ime</td>
                            <td style="padding:12px 0;color:#111;font-size:14px;font-weight:bold;text-align:right;">{user_name}</td>
                        </tr>
                        <tr>
                            <td style="padding:12px 0;color:#777;font-size:14px;">Email</td>
                            <td style="padding:12px 0;color:#111;font-size:14px;font-weight:bold;text-align:right;">{user_email}</td>
                        </tr>
                        <tr>
                            <td style="padding:12px 0;color:#777;font-size:14px;">Telefon</td>
                            <td style="padding:12px 0;color:#111;font-size:14px;font-weight:bold;text-align:right;">{user_phone}</td>
                        </tr>
                        <tr>
                            <td style="padding:12px 0;color:#777;font-size:14px;">Datum</td>
                            <td style="padding:12px 0;color:#111;font-size:14px;font-weight:bold;text-align:right;">{term_date}</td>
                        </tr>
                        <tr>
                            <td style="padding:12px 0;color:#777;font-size:14px;">Ura</td>
                            <td style="padding:12px 0;color:#111;font-size:14px;font-weight:bold;text-align:right;">{term_time}</td>
                        </tr>
                        <tr>
                            <td style="padding:12px 0;color:#777;font-size:14px;">Storitev</td>
                            <td style="padding:12px 0;color:#111;font-size:14px;font-weight:bold;text-align:right;">{hairstyle}</td>
                        </tr>
                    </table>
                </div>
            </div>

            <div style="padding:18px 20px;text-align:center;background:#ece8df;color:#8b8b8b;font-size:12px;">
                Budi Blendz Admin • Samodejno sistemsko obvestilo
            </div>
        </div>
    </div>
    """

    try:
        print("Pošiljam email uporabniku:", user_email)
        send_sendgrid_email(
            to_email=user_email,
            subject="Potrditev rezervacije - Budi Blendz",
            plain_body=user_plain,
            html_body=user_html
        )
        print("Email uporabniku uspešno poslan:", user_email)
    except Exception:
        print("===== NAPAKA USER EMAIL =====")
        traceback.print_exc()

    try:
        print("Pošiljam email adminu:", ADMIN_EMAIL)
        send_sendgrid_email(
            to_email=ADMIN_EMAIL,
            subject="Nova rezervacija termina - Budi Blendz",
            plain_body=admin_plain,
            html_body=admin_html
        )
        print("Email adminu uspešno poslan:", ADMIN_EMAIL)
    except Exception:
        print("===== NAPAKA ADMIN EMAIL =====")
        traceback.print_exc()

    return True

# ------------------ ROUTES ------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "").strip()

        if not name or not email or not phone or not password:
            flash("Vsa polja so obvezna.")
            return redirect("/register")

        if "@" not in email or "." not in email:
            flash("Vnesi veljaven email naslov.")
            return redirect("/register")

        if len(password) < 6:
            flash("Geslo mora imeti vsaj 6 znakov.")
            return redirect("/register")

        hashed_password = generate_password_hash(password)

        db = get_db()
        cursor = db.cursor()

        try:
            cursor.execute("""
                INSERT INTO users (name, email, password, phone, role)
                VALUES (?, ?, ?, ?, ?)
            """, (name, email, hashed_password, phone, "user"))
            db.commit()
            flash("Registracija je uspela. Zdaj se prijavi.")
        except sqlite3.IntegrityError:
            flash("Uporabnik s tem emailom že obstaja.")
            db.close()
            return redirect("/register")

        db.close()
        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cursor.fetchone()
        db.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["email"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            flash("Uspešno si se prijavil.")
            return redirect("/")

        flash("Napačen email ali geslo.")
        return redirect("/login")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Uspešno si se odjavil.")
    return redirect("/")


@app.route("/booking")
def booking():
    if "user" not in session:
        flash("Za rezervacijo se moraš prijaviti.")
        return redirect("/login")

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM terms ORDER BY date, time")
    terms = cursor.fetchall()
    db.close()

    dnevi = pripravi_dneve_za_prikaz(terms, 14)
    return render_template("booking.html", dnevi=dnevi)


@app.route("/reserve/<int:id>", methods=["POST"])
def reserve(id):
    if "user" not in session:
        flash("Za rezervacijo se moraš prijaviti.")
        return redirect("/login")

    hairstyle = request.form.get("hairstyle", "").strip()

    if not hairstyle:
        flash("Izberi ali vpiši vrsto frizure.")
        return redirect("/booking")

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM terms WHERE id=?", (id,))
    termin = cursor.fetchone()

    if not termin:
        db.close()
        flash("Termin ne obstaja.")
        return redirect("/booking")

    if termin["status"] != "free":
        db.close()
        flash("Ta termin je že rezerviran.")
        return redirect("/booking")

    cursor.execute("SELECT name, phone FROM users WHERE email=?", (session["user"],))
    user_data = cursor.fetchone()

    user_name = user_data["name"] if user_data and user_data["name"] else "Uporabnik"
    user_phone = user_data["phone"] if user_data and user_data["phone"] else "Ni telefona"

    cursor.execute("""
        UPDATE terms
        SET status='reserved', hairstyle=?, user_email=?
        WHERE id=? AND status='free'
    """, (hairstyle, session["user"], id))

    if cursor.rowcount == 0:
        db.close()
        flash("Ta termin je bil medtem že rezerviran.")
        return redirect("/booking")

    db.commit()
    db.close()

    print("Rezervacija uspešna, pošiljam email...")

    try:
        send_booking_emails(
            user_email=session["user"],
            user_name=user_name,
            user_phone=user_phone,
            term_date=termin["date"],
            term_time=termin["time"],
            hairstyle=hairstyle
        )
    except Exception:
        print("===== NAPAKA V RESERVE EMAIL DELU =====")
        traceback.print_exc()

    flash("Termin je bil uspešno rezerviran.")
    return redirect("/booking")


@app.route("/admin")
def admin():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM terms ORDER BY date, time")
    terms = cursor.fetchall()
    db.close()

    dnevi = pripravi_dneve_za_prikaz(terms, 14)
    return render_template("admin.html", dnevi=dnevi)


@app.route("/add-term", methods=["POST"])
def add_term():
    if session.get("role") != "admin":
        return "Ni dovoljeno"

    date = request.form.get("date", "").strip()
    time = request.form.get("time", "").strip()

    if not date or not time:
        flash("Datum in ura sta obvezna.")
        return redirect("/admin")

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM terms WHERE date=? AND time=?", (date, time))
    obstaja = cursor.fetchone()

    if obstaja:
        db.close()
        flash("Ta termin že obstaja.")
        return redirect("/admin")

    cursor.execute("""
        INSERT INTO terms (date, time, hairstyle, status, user_email)
        VALUES (?, ?, '', 'free', '')
    """, (date, time))

    db.commit()
    db.close()

    flash("Termin je bil dodan.")
    return redirect("/admin")


@app.route("/dodaj-teden", methods=["POST"])
def dodaj_teden():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    monday_date = request.form.get("monday_date", "").strip()

    if not monday_date:
        flash("Datum ponedeljka manjka.")
        return redirect("/admin")

    zacetek_tedna = datetime.strptime(monday_date, "%Y-%m-%d")

    ustvari_dneve(zacetek_tedna, 7)
    flash("Teden je bil uspešno dodan.")
    return redirect("/admin")


@app.route("/dodaj-trenutni-teden")
def dodaj_trenutni_teden():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    danes = datetime.today()
    zacetek_tedna = danes - timedelta(days=danes.weekday())

    ustvari_dneve(zacetek_tedna, 7)
    flash("Trenutni teden je bil dodan.")
    return redirect("/admin")


@app.route("/dodaj-naslednji-teden")
def dodaj_naslednji_teden():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    danes = datetime.today()
    zacetek_tedna = danes - timedelta(days=danes.weekday()) + timedelta(days=7)

    ustvari_dneve(zacetek_tedna, 7)
    flash("Naslednji teden je bil dodan.")
    return redirect("/admin")


@app.route("/dodaj-dva-tedna")
def dodaj_dva_tedna():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    danes = datetime.today()
    zacetek_tedna = danes - timedelta(days=danes.weekday())

    ustvari_dneve(zacetek_tedna, 14)
    flash("Dodana sta bila 2 tedna terminov.")
    return redirect("/admin")


@app.route("/delete-term/<int:id>")
def delete_term(id):
    if session.get("role") != "admin":
        return "Ni dovoljeno"

    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM terms WHERE id=?", (id,))
    db.commit()
    db.close()

    flash("Termin je bil izbrisan.")
    return redirect("/admin")


@app.route("/izbrisi-vse-termine")
def izbrisi_vse_termine():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM terms")
    db.commit()
    db.close()

    flash("Vsi termini so bili izbrisani.")
    return redirect("/admin")


@app.route("/galerija")
def gallery():
    return render_template("galerija.html")


@app.route("/trgovina")
def shop():
    return render_template("trgovina.html")


@app.route("/kontakt")
def contact():
    return render_template("kontakt.html")


@app.route("/lokacija")
def location():
    return render_template("lokacija.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)