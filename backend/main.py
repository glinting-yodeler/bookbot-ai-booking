from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import hashlib
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

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


def create_notification(message):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO notifications (message, created_at) VALUES (?, datetime('now'))",
        (message,)
    )

    conn.commit()
    conn.close()


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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            created_at TEXT
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


@app.head("/")
def health_check():
    return


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

        create_notification("New " + role + " account created for " + name)

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

    create_notification("Admin added a new slot on " + date + " at " + time)

    return {
        "success": True,
        "message": "Slot added successfully"
    }


@app.delete("/slots/{slot_id}")
def delete_slot(slot_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT date, time, is_booked FROM slots WHERE id = ?", (slot_id,))
    slot = cursor.fetchone()

    if slot is None:
        conn.close()

        return {
            "success": False,
            "message": "Slot not found"
        }

    if slot[2] == 1:
        conn.close()

        return {
            "success": False,
            "message": "Cannot delete a booked slot"
        }

    slot_date = slot[0]
    slot_time = slot[1]

    cursor.execute("DELETE FROM slots WHERE id = ?", (slot_id,))

    conn.commit()
    conn.close()

    create_notification("Admin deleted Slot ID " + str(slot_id) + " on " + slot_date + " at " + slot_time)

    return {
        "success": True,
        "message": "Slot deleted successfully"
    }


@app.post("/bookings")
def create_booking(user_id: int, slot_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    if user is None:
        conn.close()

        return {
            "success": False,
            "message": "User not found"
        }

    cursor.execute("SELECT id, date, time, is_booked FROM slots WHERE id = ?", (slot_id,))
    slot = cursor.fetchone()

    if slot is None:
        conn.close()

        return {
            "success": False,
            "message": "Slot not found"
        }

    if slot[3] == 1:
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

    customer_name = user[1]
    slot_date = slot[1]
    slot_time = slot[2]

    create_notification(
        customer_name + " booked Slot ID " + str(slot_id) + " on " + slot_date + " at " + slot_time
    )

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

    cursor.execute("""
        SELECT bookings.slot_id, bookings.status, users.name, slots.date, slots.time
        FROM bookings
        JOIN users ON bookings.user_id = users.id
        JOIN slots ON bookings.slot_id = slots.id
        WHERE bookings.id = ?
    """, (booking_id,))

    booking = cursor.fetchone()

    if booking is None:
        conn.close()

        return {
            "success": False,
            "message": "Booking not found"
        }

    slot_id = booking[0]
    customer_name = booking[2]
    slot_date = booking[3]
    slot_time = booking[4]

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

    create_notification(
        customer_name + " cancelled Booking ID " + str(booking_id) + " for " + slot_date + " at " + slot_time
    )

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

    cursor.execute("SELECT COUNT(*) FROM notifications")
    total_notifications = cursor.fetchone()[0]

    conn.close()

    return {
        "total_customers": total_customers,
        "total_slots": total_slots,
        "available_slots": available_slots,
        "confirmed_bookings": confirmed_bookings,
        "cancelled_bookings": cancelled_bookings,
        "total_notifications": total_notifications
    }


@app.get("/notifications")
def get_notifications():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, message, created_at
        FROM notifications
        ORDER BY id DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()

    conn.close()

    notifications = []

    for row in rows:
        notifications.append({
            "id": row[0],
            "message": row[1],
            "created_at": row[2]
        })

    return notifications


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


@app.post("/ai-chat")
def ai_chat(user_id: int, message: str):
    try:
        groq_key = os.getenv("GROQ_API_KEY")

        if groq_key is None or groq_key == "":
            return {
                "success": False,
                "reply": "Groq API key is missing. Please add GROQ_API_KEY in your .env file or Render environment variables.",
                "error": "Missing GROQ_API_KEY"
            }

        available_slots = get_available_slots()
        user_bookings = get_my_bookings(user_id)

        system_prompt = """
You are BookBot, a helpful AI booking assistant for a local booking SaaS.

Your job:
- Help users understand available slots.
- Recommend suitable slots.
- Explain how to book.
- Explain how to cancel.
- Answer only using the booking data given to you.

Rules:
- Do not invent slots.
- Do not say a slot exists unless it appears in available_slots.
- If the user wants to book, tell them the exact Slot ID they should click.
- If the user wants to cancel, tell them to use the cancel button in My Bookings.
- Keep replies short and practical.
"""

        data_context = f"""
Available slots:
{available_slots}

User bookings:
{user_bookings}
"""

        groq_client = Groq(api_key=groq_key)

        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": data_context
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
            temperature=0.3,
            max_tokens=300
        )

        reply = completion.choices[0].message.content

        return {
            "success": True,
            "reply": reply
        }

    except Exception as e:
        return {
            "success": False,
            "reply": "AI assistant is unavailable right now. Please try again later.",
            "error": str(e)
        }