from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import hashlib

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "bookbot.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    return conn


def hash_password(password):
    password_bytes = password.encode()
    hashed = hashlib.sha256(password_bytes).hexdigest()
    return hashed


def setup_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            time TEXT,
            is_booked INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            slot_id INTEGER,
            status TEXT
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM slots")
    slot_count = cursor.fetchone()[0]

    if slot_count == 0:
        sample_slots = [
            ("2026-05-27", "18:00", 0),
            ("2026-05-27", "19:00", 0),
            ("2026-05-27", "20:00", 0),
            ("2026-05-28", "18:00", 0),
            ("2026-05-28", "19:00", 0),
            ("2026-05-28", "20:00", 0),
        ]

        cursor.executemany(
            "INSERT INTO slots (date, time, is_booked) VALUES (?, ?, ?)",
            sample_slots
        )

    admin_email = "admin@bookbot.com"
    admin_password = hash_password("admin123")

    cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
    existing_admin = cursor.fetchone()

    if existing_admin is None:
        cursor.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
            ("Admin", admin_email, admin_password, "admin")
        )

    conn.commit()
    conn.close()


setup_database()


@app.get("/")
def home():
    return {
        "message": "BookBot backend is running"
    }


@app.post("/register")
def register(name: str, email: str, password: str, role: str = "customer"):
    conn = get_connection()
    cursor = conn.cursor()

    hashed_password = hash_password(password)

    try:
        cursor.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
            (name, email, hashed_password, role)
        )

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "Account created successfully"
        }

    except sqlite3.IntegrityError:
        conn.close()

        return {
            "success": False,
            "message": "Email already exists"
        }


@app.post("/login")
def login(email: str, password: str):
    conn = get_connection()
    cursor = conn.cursor()

    hashed_password = hash_password(password)

    cursor.execute(
        "SELECT id, name, email, role FROM users WHERE email = ? AND password = ?",
        (email, hashed_password)
    )

    user = cursor.fetchone()

    conn.close()

    if user is None:
        return {
            "success": False,
            "message": "Invalid email or password"
        }

    return {
        "success": True,
        "message": "Login successful",
        "user": {
            "id": user[0],
            "name": user[1],
            "email": user[2],
            "role": user[3]
        }
    }


@app.get("/slots")
def get_slots():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, date, time, is_booked FROM slots ORDER BY date, time")
    rows = cursor.fetchall()

    conn.close()

    slots = []

    for row in rows:
        slots.append({
            "id": row[0],
            "date": row[1],
            "time": row[2],
            "is_booked": bool(row[3])
        })

    return slots


@app.get("/available-slots")
def get_available_slots():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, date, time, is_booked FROM slots WHERE is_booked = 0 ORDER BY date, time"
    )

    rows = cursor.fetchall()

    conn.close()

    slots = []

    for row in rows:
        slots.append({
            "id": row[0],
            "date": row[1],
            "time": row[2],
            "is_booked": bool(row[3])
        })

    return slots


@app.post("/slots")
def add_slot(date: str, time: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO slots (date, time, is_booked) VALUES (?, ?, ?)",
        (date, time, 0)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Slot added successfully"
    }


@app.delete("/slots/{slot_id}")
def delete_slot(slot_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT is_booked FROM slots WHERE id = ?", (slot_id,))
    slot = cursor.fetchone()

    if slot is None:
        conn.close()

        return {
            "success": False,
            "message": "Slot not found"
        }

    if slot[0] == 1:
        conn.close()

        return {
            "success": False,
            "message": "Cannot delete a booked slot"
        }

    cursor.execute("DELETE FROM slots WHERE id = ?", (slot_id,))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Slot deleted successfully"
    }


@app.post("/bookings")
def create_booking(user_id: int, slot_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    if user is None:
        conn.close()

        return {
            "success": False,
            "message": "User not found"
        }

    cursor.execute("SELECT id, is_booked FROM slots WHERE id = ?", (slot_id,))
    slot = cursor.fetchone()

    if slot is None:
        conn.close()

        return {
            "success": False,
            "message": "Slot not found"
        }

    if slot[1] == 1:
        conn.close()

        return {
            "success": False,
            "message": "Slot already booked"
        }

    cursor.execute(
        "INSERT INTO bookings (user_id, slot_id, status) VALUES (?, ?, ?)",
        (user_id, slot_id, "confirmed")
    )

    cursor.execute(
        "UPDATE slots SET is_booked = 1 WHERE id = ?",
        (slot_id,)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Booking confirmed successfully"
    }


@app.get("/bookings")
def get_all_bookings():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT bookings.id, users.name, users.email, bookings.slot_id,
               bookings.status, slots.date, slots.time
        FROM bookings
        JOIN users ON bookings.user_id = users.id
        JOIN slots ON bookings.slot_id = slots.id
        ORDER BY bookings.id DESC
    """)

    rows = cursor.fetchall()

    conn.close()

    bookings = []

    for row in rows:
        bookings.append({
            "id": row[0],
            "customer_name": row[1],
            "customer_email": row[2],
            "slot_id": row[3],
            "status": row[4],
            "date": row[5],
            "time": row[6]
        })

    return bookings


@app.get("/my-bookings/{user_id}")
def get_my_bookings(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT bookings.id, bookings.slot_id, bookings.status,
               slots.date, slots.time
        FROM bookings
        JOIN slots ON bookings.slot_id = slots.id
        WHERE bookings.user_id = ?
        ORDER BY bookings.id DESC
    """, (user_id,))

    rows = cursor.fetchall()

    conn.close()

    bookings = []

    for row in rows:
        bookings.append({
            "id": row[0],
            "slot_id": row[1],
            "status": row[2],
            "date": row[3],
            "time": row[4]
        })

    return bookings


@app.delete("/bookings/{booking_id}")
def cancel_booking(booking_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT slot_id, status FROM bookings WHERE id = ?", (booking_id,))
    booking = cursor.fetchone()

    if booking is None:
        conn.close()

        return {
            "success": False,
            "message": "Booking not found"
        }

    slot_id = booking[0]

    cursor.execute(
        "UPDATE bookings SET status = ? WHERE id = ?",
        ("cancelled", booking_id)
    )

    cursor.execute(
        "UPDATE slots SET is_booked = 0 WHERE id = ?",
        (slot_id,)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Booking cancelled successfully"
    }


@app.get("/analytics")
def get_analytics():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'")
    total_customers = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM slots")
    total_slots = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM slots WHERE is_booked = 0")
    available_slots = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM bookings WHERE status = 'confirmed'")
    confirmed_bookings = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM bookings WHERE status = 'cancelled'")
    cancelled_bookings = cursor.fetchone()[0]

    conn.close()

    return {
        "total_customers": total_customers,
        "total_slots": total_slots,
        "available_slots": available_slots,
        "confirmed_bookings": confirmed_bookings,
        "cancelled_bookings": cancelled_bookings
    }


@app.post("/chat")
def chat(message: str):
    lower_message = message.lower()

    if "available" in lower_message or "slot" in lower_message or "time" in lower_message:
        slots = get_available_slots()

        return {
            "reply": "These slots are currently available.",
            "available_slots": slots
        }

    if "book" in lower_message:
        return {
            "reply": "To book, choose an available slot and press the Book button."
        }

    if "cancel" in lower_message:
        return {
            "reply": "You can cancel a booking from your booking history."
        }

    if "admin" in lower_message:
        return {
            "reply": "Admin can add slots, delete slots, view bookings, and check analytics."
        }

    return {
        "reply": "Hi, I am BookBot. I can help you view slots, book a slot, or cancel a booking."
    }