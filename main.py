from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"

# ------------------ DATABASE ------------------
def get_db():
    return sqlite3.connect("database.db")

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

# ------------------ HOME ------------------
@app.route("/")
def index():
    return render_template("index.html")

# ------------------ REGISTER ------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        role = "user"

        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                       (name, email, password, role))
        db.commit()
        db.close()

        return redirect("/login")

    return render_template("register.html")

# ------------------ LOGIN ------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
        user = cursor.fetchone()

        if user:
            session["user"] = user[2]
            session["role"] = user[4]
            return redirect("/")

    return render_template("login.html")

# ------------------ LOGOUT ------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ------------------ BOOKING ------------------
@app.route("/booking")
def booking():
    if "user" not in session:
        return redirect("/login")

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM terms WHERE status='free'")
    terms = cursor.fetchall()
    db.close()

    return render_template("booking.html", terms=terms)

# ------------------ RESERVE ------------------
@app.route("/reserve/<int:id>", methods=["POST"])
def reserve(id):
    if "user" not in session:
        return redirect("/login")

    hairstyle = request.form["hairstyle"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("UPDATE terms SET status='reserved', hairstyle=?, user_email=? WHERE id=?",
                   (hairstyle, session["user"], id))

    db.commit()
    db.close()

    return redirect("/booking")

# ------------------ ADMIN ------------------
@app.route("/admin")
def admin():
    if "user" not in session or session["role"] != "admin":
        return "Dostop zavrnjen"

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM terms")
    terms = cursor.fetchall()
    db.close()

    return render_template("admin.html", terms=terms)

# ------------------ ADD TERM ------------------
@app.route("/add-term", methods=["POST"])
def add_term():
    if session.get("role") != "admin":
        return "Ni dovoljeno"

    date = request.form["date"]
    time = request.form["time"]

    db = get_db()
    cursor = db.cursor()

    cursor.execute("INSERT INTO terms (date, time, hairstyle, status, user_email) VALUES (?, ?, '', 'free', '')",
                   (date, time))

    db.commit()
    db.close()

    return redirect("/admin")

# ------------------ DELETE TERM ------------------
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

# ------------------ RUN ------------------
if __name__ == "__main__":
    app.run(debug=True)