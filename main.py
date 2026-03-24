from flask import Flask, render_template, request, redirect, session, flash
from flask_mail import Mail, Message
import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "zamenjaj_to_z_mocnejsim_kljucem"

# ------------------ MAIL CONFIG ------------------
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = "zak.bernik07@gmail.com"
app.config["MAIL_PASSWORD"] = "aqjguvgabjftfcxf"
app.config["MAIL_DEFAULT_SENDER"] = "zak.bernik07@gmail.com"

mail = Mail(app)
ADMIN_EMAIL = "zak.bernik07@gmail.com"

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

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        db.commit()
        print("Phone stolpec dodan.")
    except sqlite3.OperationalError:
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

    ure = ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"]

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
def attach_logo_if_exists(msg):
    logo_path = os.path.join(app.root_path, "static", "images", "logo.jpg")

    if os.path.exists(logo_path):
        with open(logo_path, "rb") as logo_file:
            msg.attach(
                filename="logo.jpg",
                content_type="image/jpeg",
                data=logo_file.read(),
                disposition="inline",
                headers={"Content-ID": "<logo_image>"}
            )
    else:
        print("Logo ni najden:", logo_path)


def send_booking_emails(user_email, user_name, user_phone, term_date, term_time, hairstyle):
    try:
        # ------------------ USER EMAIL ------------------
        user_msg = Message(
            subject="Potrditev rezervacije - Budi Blendz",
            recipients=[user_email]
        )

        user_msg.body = f"""Pozdravljen {user_name},

tvoj termin je uspešno rezerviran.

Datum: {term_date}
Ura: {term_time}
Storitev: {hairstyle}
Telefon: {user_phone}

Hvala za rezervacijo.
Budi Blendz
"""

        user_msg.html = f"""
        <div style="margin:0;padding:40px 20px;background:#f5f5f5;font-family:Arial,sans-serif;">
            <div style="max-width:620px;margin:0 auto;background:#ffffff;border-radius:22px;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,0.10);">

                <div style="background:#111111;padding:38px 30px;text-align:center;">
                    <img src="cid:logo_image" alt="Budi Blendz logo" style="max-width:180px;width:100%;height:auto;margin:0 auto 14px auto;display:block;">
                    <div style="font-size:14px;letter-spacing:4px;text-transform:uppercase;color:#c9a227;margin-bottom:12px;">
                        Premium Barber Experience
                    </div>
                    <h1 style="margin:0;font-size:34px;color:#ffffff;font-weight:800;">
                        Budi Blendz
                    </h1>
                    <p style="margin:12px 0 0 0;color:#d4d4d4;font-size:15px;">
                        Potrditev uspešne rezervacije
                    </p>
                </div>

                <div style="padding:36px 32px;">
                    <p style="margin-top:0;font-size:17px;color:#111111;">
                        Pozdravljen <strong>{user_name}</strong>,
                    </p>

                    <p style="font-size:15px;line-height:1.7;color:#555555;">
                        tvoj termin je uspešno rezerviran. Spodaj so vse podrobnosti rezervacije.
                    </p>

                    <div style="margin:28px 0;padding:24px;background:#fcfaf3;border:1px solid #ead38c;border-radius:18px;">
                        <table style="width:100%;border-collapse:collapse;">
                            <tr>
                                <td style="padding:10px 0;font-size:15px;color:#777777;">Datum</td>
                                <td style="padding:10px 0;font-size:15px;color:#111111;font-weight:bold;text-align:right;">{term_date}</td>
                            </tr>
                            <tr>
                                <td style="padding:10px 0;font-size:15px;color:#777777;">Ura</td>
                                <td style="padding:10px 0;font-size:15px;color:#111111;font-weight:bold;text-align:right;">{term_time}</td>
                            </tr>
                            <tr>
                                <td style="padding:10px 0;font-size:15px;color:#777777;">Storitev</td>
                                <td style="padding:10px 0;font-size:15px;color:#111111;font-weight:bold;text-align:right;">{hairstyle}</td>
                            </tr>
                            <tr>
                                <td style="padding:10px 0;font-size:15px;color:#777777;">Telefon</td>
                                <td style="padding:10px 0;font-size:15px;color:#111111;font-weight:bold;text-align:right;">{user_phone}</td>
                            </tr>
                        </table>
                    </div>

                    <div style="text-align:center;margin:30px 0 10px 0;">
                        <span style="display:inline-block;background:#c9a227;color:#ffffff;padding:14px 26px;border-radius:999px;font-weight:bold;font-size:14px;letter-spacing:0.4px;">
                            Rezervacija potrjena
                        </span>
                    </div>
                </div>

                <div style="background:#fafafa;padding:22px 30px;text-align:center;border-top:1px solid #eeeeee;">
                    <p style="margin:0;font-size:13px;color:#888888;">Budi Blendz</p>
                    <p style="margin:8px 0 0 0;font-size:12px;color:#aaaaaa;">Samodejno poslano ob uspešni rezervaciji termina</p>
                </div>
            </div>
        </div>
        """

        attach_logo_if_exists(user_msg)
        mail.send(user_msg)

        # ------------------ ADMIN EMAIL ------------------
        admin_msg = Message(
            subject="Nova rezervacija termina - Budi Blendz",
            recipients=[ADMIN_EMAIL]
        )

        admin_msg.body = f"""Nova rezervacija termina

Ime: {user_name}
Email: {user_email}
Telefon: {user_phone}
Datum: {term_date}
Ura: {term_time}
Storitev: {hairstyle}
"""

        admin_msg.html = f"""
        <div style="margin:0;padding:40px 20px;background:#f5f5f5;font-family:Arial,sans-serif;">
            <div style="max-width:620px;margin:0 auto;background:#ffffff;border-radius:22px;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,0.10);">

                <div style="background:linear-gradient(135deg, #111111, #1f1f1f);padding:38px 30px;text-align:center;">
                    <img src="cid:logo_image" alt="Budi Blendz logo" style="max-width:170px;width:100%;height:auto;margin:0 auto 14px auto;display:block;background:#ffffff;padding:10px;border-radius:14px;">
                    <div style="font-size:14px;letter-spacing:4px;text-transform:uppercase;color:#c9a227;margin-bottom:12px;">
                        Admin Notification
                    </div>
                    <h1 style="margin:0;font-size:32px;color:#ffffff;font-weight:800;">
                        Nova rezervacija
                    </h1>
                    <p style="margin:12px 0 0 0;color:#d4d4d4;font-size:15px;">
                        Budi Blendz sistemsko obvestilo
                    </p>
                </div>

                <div style="padding:36px 32px;">
                    <p style="margin-top:0;font-size:17px;color:#111111;">
                        Rezerviran je nov termin.
                    </p>

                    <div style="margin:28px 0;padding:24px;background:#fcfaf3;border:1px solid #ead38c;border-radius:18px;">
                        <table style="width:100%;border-collapse:collapse;">
                            <tr>
                                <td style="padding:10px 0;font-size:15px;color:#777777;">Ime</td>
                                <td style="padding:10px 0;font-size:15px;color:#111111;font-weight:bold;text-align:right;">{user_name}</td>
                            </tr>
                            <tr>
                                <td style="padding:10px 0;font-size:15px;color:#777777;">Email</td>
                                <td style="padding:10px 0;font-size:15px;color:#111111;font-weight:bold;text-align:right;">{user_email}</td>
                            </tr>
                            <tr>
                                <td style="padding:10px 0;font-size:15px;color:#777777;">Telefon</td>
                                <td style="padding:10px 0;font-size:15px;color:#111111;font-weight:bold;text-align:right;">{user_phone}</td>
                            </tr>
                            <tr>
                                <td style="padding:10px 0;font-size:15px;color:#777777;">Datum</td>
                                <td style="padding:10px 0;font-size:15px;color:#111111;font-weight:bold;text-align:right;">{term_date}</td>
                            </tr>
                            <tr>
                                <td style="padding:10px 0;font-size:15px;color:#777777;">Ura</td>
                                <td style="padding:10px 0;font-size:15px;color:#111111;font-weight:bold;text-align:right;">{term_time}</td>
                            </tr>
                            <tr>
                                <td style="padding:10px 0;font-size:15px;color:#777777;">Storitev</td>
                                <td style="padding:10px 0;font-size:15px;color:#111111;font-weight:bold;text-align:right;">{hairstyle}</td>
                            </tr>
                        </table>
                    </div>
                </div>

                <div style="background:#fafafa;padding:22px 30px;text-align:center;border-top:1px solid #eeeeee;">
                    <p style="margin:0;font-size:13px;color:#888888;">Budi Blendz Admin</p>
                    <p style="margin:8px 0 0 0;font-size:12px;color:#aaaaaa;">Samodejno sistemsko obvestilo</p>
                </div>
            </div>
        </div>
        """

        attach_logo_if_exists(admin_msg)
        mail.send(admin_msg)

    except Exception as e:
        print("Napaka pri pošiljanju emaila:", e)

# ------------------ ROUTES ------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form["phone"].strip()
        password = request.form["password"].strip()

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
        email = request.form["email"].strip().lower()
        password = request.form["password"].strip()

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

    hairstyle = request.form["hairstyle"].strip()

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
    """, (hairstyle, f"{session['user']} | {user_phone}", id))

    db.commit()
    db.close()

    send_booking_emails(
        user_email=session["user"],
        user_name=user_name,
        user_phone=user_phone,
        term_date=termin["date"],
        term_time=termin["time"],
        hairstyle=hairstyle
    )

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

    date = request.form["date"].strip()
    time = request.form["time"].strip()

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

    monday_date = request.form["monday_date"]
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


# ZAČASNO - PO TEM IZBRIŠI
@app.route("/make-admin")
def make_admin():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE users SET role='admin' WHERE email=?", ("zak.bernik07@gmail.com",))
    db.commit()
    db.close()
    return "Zdaj si admin"


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
    app.run(host="0.0.0.0", port=5000, debug=True)