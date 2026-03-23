from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "secret123"

# ------------------ SLOVENSKI DNEVI ------------------
DNEVI = {
    0: "Ponedeljek",
    1: "Torek",
    2: "Sreda",
    3: "Četrtek",
    4: "Petek",
    5: "Sobota",
    6: "Nedelja"
}

# ------------------ POVEZAVA NA BAZO ------------------
def get_db():
    return sqlite3.connect("database.db")

# ------------------ USTVARJANJE BAZE ------------------
def init_db():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        password TEXT,
        role TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS terms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        time TEXT,
        hairstyle TEXT,
        status TEXT,
        user_email TEXT
    )
    """)

    db.commit()
    db.close()

init_db()

# ------------------ GRUPIRANJE TERMINOV PO DNEVIH ------------------
def grupiraj_termine_po_dnevih(termini):
    rezultat = []

    po_dnevih = {}

    for termin in termini:
        termin_id = termin[0]
        datum = termin[1]
        ura = termin[2]
        frizura = termin[3]
        status = termin[4]
        user_email = termin[5]

        datum_obj = datetime.strptime(datum, "%Y-%m-%d")
        ime_dneva = DNEVI[datum_obj.weekday()]
        kljuc = datum

        if kljuc not in po_dnevih:
            po_dnevih[kljuc] = {
                "datum": datum,
                "ime_dneva": ime_dneva,
                "termini": []
            }

        po_dnevih[kljuc]["termini"].append({
            "id": termin_id,
            "date": datum,
            "time": ura,
            "hairstyle": frizura,
            "status": status,
            "user_email": user_email
        })

    for datum in sorted(po_dnevih.keys()):
        rezultat.append(po_dnevih[datum])

    return rezultat

# ------------------ POMOŽNA FUNKCIJA ZA USTVARJANJE VEČ DNI ------------------
def ustvari_dneve(zacetek_dneva, stevilo_dni):
    db = get_db()
    cursor = db.cursor()

    ure = ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"]

    for i in range(stevilo_dni):
        dan = zacetek_dneva + timedelta(days=i)
        datum = dan.strftime("%Y-%m-%d")

        for ura in ure:
            cursor.execute("SELECT * FROM terms WHERE date=? AND time=?", (datum, ura))
            obstaja = cursor.fetchone()

            if not obstaja:
                cursor.execute("""
                    INSERT INTO terms (date, time, hairstyle, status, user_email)
                    VALUES (?, ?, '', 'free', '')
                """, (datum, ura))

    db.commit()
    db.close()

# ------------------ DOMOV ------------------
@app.route("/")
def index():
    return render_template("index.html")

# ------------------ REGISTRACIJA ------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        role = "user"

        db = get_db()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, ?)
        """, (name, email, password, role))

        db.commit()
        db.close()

        return redirect("/login")

    return render_template("register.html")

# ------------------ PRIJAVA ------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor()

        cursor.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
        user = cursor.fetchone()

        db.close()

        if user:
            session["user"] = user[2]
            session["role"] = user[4]
            return redirect("/")

    return render_template("login.html")

# ------------------ ODJAVA ------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ------------------ REZERVACIJA STRAN ------------------
@app.route("/booking")
def booking():
    if "user" not in session:
        return redirect("/login")

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM terms WHERE status='free' ORDER BY date, time")
    terms = cursor.fetchall()

    db.close()

    dnevi = grupiraj_termine_po_dnevih(terms)

    return render_template("booking.html", dnevi=dnevi)

# ------------------ REZERVACIJA TERMINA ------------------
@app.route("/reserve/<int:id>", methods=["POST"])
def reserve(id):
    if "user" not in session:
        return redirect("/login")

    hairstyle = request.form["hairstyle"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        UPDATE terms
        SET status='reserved', hairstyle=?, user_email=?
        WHERE id=?
    """, (hairstyle, session["user"], id))

    db.commit()
    db.close()

    return redirect("/booking")

# ------------------ ADMIN PANEL ------------------
@app.route("/admin")
def admin():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM terms ORDER BY date, time")
    terms = cursor.fetchall()

    db.close()

    dnevi = grupiraj_termine_po_dnevih(terms)

    return render_template("admin.html", dnevi=dnevi)

# ------------------ DODAJ POSAMEZEN TERMIN ------------------
@app.route("/add-term", methods=["POST"])
def add_term():
    if session.get("role") != "admin":
        return "Ni dovoljeno"

    date = request.form["date"]
    time = request.form["time"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT * FROM terms WHERE date=? AND time=?", (date, time))
    obstaja = cursor.fetchone()

    if not obstaja:
        cursor.execute("""
            INSERT INTO terms (date, time, hairstyle, status, user_email)
            VALUES (?, ?, '', 'free', '')
        """, (date, time))
        db.commit()

    db.close()

    return redirect("/admin")

# ------------------ DODAJ IZBRAN TEDEN ------------------
@app.route("/dodaj-teden", methods=["POST"])
def dodaj_teden():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    monday_date = request.form["monday_date"]
    zacetek_tedna = datetime.strptime(monday_date, "%Y-%m-%d")

    ustvari_dneve(zacetek_tedna, 7)

    return redirect("/admin")

# ------------------ DODAJ TRENUTNI TEDEN ------------------
@app.route("/dodaj-trenutni-teden")
def dodaj_trenutni_teden():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    danes = datetime.today()
    zacetek_tedna = danes - timedelta(days=danes.weekday())

    ustvari_dneve(zacetek_tedna, 7)

    return redirect("/admin")

# ------------------ DODAJ NASLEDNJI TEDEN ------------------
@app.route("/dodaj-naslednji-teden")
def dodaj_naslednji_teden():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    danes = datetime.today()
    zacetek_tedna = danes - timedelta(days=danes.weekday()) + timedelta(days=7)

    ustvari_dneve(zacetek_tedna, 7)

    return redirect("/admin")

# ------------------ DODAJ 2 TEDNA ------------------
@app.route("/dodaj-dva-tedna")
def dodaj_dva_tedna():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    danes = datetime.today()
    zacetek_tedna = danes - timedelta(days=danes.weekday())

    ustvari_dneve(zacetek_tedna, 14)

    return redirect("/admin")

# ------------------ BRISANJE TERMINA ------------------
@app.route("/delete-term/<int:id>")
def delete_term(id):
    if session.get("role") != "admin":
        return "Ni dovoljeno"

    db = get_db()
    cursor = db.cursor()

    cursor.execute("DELETE FROM terms WHERE id=?", (id,))

    db.commit()
    db.close()

    return redirect("/admin")

# ------------------ DODELITEV ADMIN VLOGE ------------------
@app.route("/make-admin")
def make_admin():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("UPDATE users SET role='admin' WHERE email='zak.bernik07@gmail.com'")

    db.commit()
    db.close()

    return "Zdaj si admin"
# ------------------ IZBRIŠI VSE TERMINE ------------------
@app.route("/izbrisi-vse-termine")
def izbrisi_vse_termine():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    db = get_db()
    cursor = db.cursor()

    cursor.execute("DELETE FROM terms")

    db.commit()
    db.close()

    return redirect("/admin")
def pripravi_dneve_za_prikaz(termini, stevilo_dni=14):
    po_dnevih = {}

    for termin in termini:
        termin_id = termin[0]
        datum = termin[1]
        ura = termin[2]
        frizura = termin[3]
        status = termin[4]
        user_email = termin[5]

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
    zacetek = danes - timedelta(days=danes.weekday())  # od ponedeljka

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

# ------------------ GALERIJA ------------------
@app.route("/galerija")
def gallery():
    return render_template("galerija.html")

# ------------------ TRGOVINA ------------------
@app.route("/trgovina")
def shop():
    return render_template("trgovina.html")

# ------------------ KONTAKT ------------------
@app.route("/kontakt")
def contact():
    return render_template("kontakt.html")

# ------------------ ZAGON ------------------
if __name__ == "__main__":
    app.run(debug=True)