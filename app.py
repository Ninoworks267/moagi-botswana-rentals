import os
import sqlite3
from functools import wraps
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, abort

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "moagi.db")
UPLOAD_DIR = os.path.join(APP_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("MOAGI_SECRET", "CHANGE-THIS-BEFORE-PUBLIC-LAUNCH")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

def init_db():
    conn = db()
    # Preserve the existing users and properties tables and all their records.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL, surname TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE, phone TEXT NOT NULL,
            password TEXT NOT NULL, role TEXT NOT NULL,
            gender TEXT, citizenship TEXT NOT NULL DEFAULT 'Botswana',
            location TEXT NOT NULL DEFAULT 'Gaborone',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER NOT NULL,
            reported_user_id INTEGER,
            property_id INTEGER,
            report_type TEXT NOT NULL,
            category TEXT NOT NULL,
            details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_status
        ON reports(status)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            landlord_id INTEGER NOT NULL, title TEXT NOT NULL,
            location TEXT NOT NULL, price REAL NOT NULL,
            bedrooms INTEGER NOT NULL, bathrooms INTEGER NOT NULL,
            description TEXT NOT NULL, photo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Add profile fields safely to older databases.
    user_cols = columns(conn, "users")
    if "profile_photo" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN profile_photo TEXT")
    if "bio" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN bio TEXT")
    if "created_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP")
    prop_cols = columns(conn, "properties")
    if "tenant_gender_pref" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN tenant_gender_pref TEXT DEFAULT 'Any'")
    if "rent_share" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN rent_share TEXT DEFAULT 'No'")
    if "bill_split" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN bill_split TEXT")
    if "yard_size" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN yard_size TEXT")
    if "parking" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN parking TEXT")
    if "fencing" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN fencing TEXT")
    if "house_rules" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN house_rules TEXT")
    if "preferred_tenant" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN preferred_tenant TEXT")
    if "electricity_meter" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN electricity_meter TEXT")
    if "water_billing" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN water_billing TEXT")
    if "water_amount" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN water_amount REAL")
    if "water_backup" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN water_backup INTEGER DEFAULT 0")
    if "deposit_terms" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN deposit_terms TEXT")
    if "nearest_shop" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN nearest_shop TEXT")
    if "shop_distance" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN shop_distance TEXT")
    if "combi_distance" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN combi_distance TEXT")
    if "road_type" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN road_type TEXT")
    if "landlord_notes" not in prop_cols:
        conn.execute("ALTER TABLE properties ADD COLUMN landlord_notes TEXT")
    # landlord profile fields
    user_cols = columns(conn, "users")
    if "deposit_refund_days" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN deposit_refund_days INTEGER")
    if "response_rate" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN response_rate REAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            landlord_id INTEGER NOT NULL,
            tenant_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(landlord_id, tenant_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            property_id INTEGER DEFAULT 0,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stay_type TEXT NOT NULL,
            title TEXT NOT NULL,
            location TEXT NOT NULL,
            price REAL NOT NULL,
            photo TEXT,
            description TEXT NOT NULL,
            rating REAL DEFAULT 4.5,
            reviews TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listing_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            is_landlord_reply INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    seed_demo(conn)
    seed_stays(conn)
    seed_houses(conn)
    conn.close()

def seed_demo(conn):
    demos = [
        ("Demo", "Landlord", "landlord@moagi.demo", "+267 71 000 001", "DemoLandlord123!", "landlord", "Gaborone", "Welcome! I list clean, well-maintained homes around Gaborone.", None),
        ("Demo", "Tenant", "tenant@moagi.demo", "+267 71 000 002", "DemoTenant123!", "tenant", "Gaborone", "I'm looking for a comfortable place to call home.", None),
        ("Kago", "Molefe", "kago@moagi.demo", "+267 71 000 003", "MoagiDemo123!", "landlord", "Francistown", "Friendly landlord with homes in Francistown.", None),
    ]
    for first, last, email, phone, password, role, location, bio, photo in demos:
        exists = conn.execute("SELECT id FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
        if not exists:
            conn.execute("""INSERT INTO users
                (first_name,surname,email,phone,password,role,citizenship,location,bio,profile_photo)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (first,last,email,phone,generate_password_hash(password),role,"Botswana",location,bio,photo))
    conn.commit()
    landlord = conn.execute("SELECT id FROM users WHERE email='landlord@moagi.demo'").fetchone()
    tenant = conn.execute("SELECT id FROM users WHERE email='tenant@moagi.demo'").fetchone()
    second = conn.execute("SELECT id FROM users WHERE email='kago@moagi.demo'").fetchone()
    if landlord:
        count = conn.execute("SELECT COUNT(*) FROM properties WHERE landlord_id=?", (landlord["id"],)).fetchone()[0]
        if count == 0:
            conn.execute("""INSERT INTO properties
                (landlord_id,title,location,price,bedrooms,bathrooms,description,photo)
                VALUES (?,?,?,?,?,?,?,?)""",
                (landlord["id"], "Modern 2-bedroom apartment", "Gaborone, Block 8", 4500, 2, 1,
                 "A bright, comfortable apartment close to shops and transport. Contact me to arrange a viewing.",
                 "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1493809842364-78817add7cfa?auto=format&fit=crop&w=1000&q=85"))
            conn.execute("""INSERT INTO properties
                (landlord_id,title,location,price,bedrooms,bathrooms,description,photo)
                VALUES (?,?,?,?,?,?,?,?)""",
                (landlord["id"], "Cosy family home", "Gaborone, Broadhurst", 6500, 3, 2,
                 "Spacious home with a relaxed living area and a small garden.",
                 "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600573472592-401b489a3cdc?auto=format&fit=crop&w=1000&q=85"))
    if second:
        count = conn.execute("SELECT COUNT(*) FROM properties WHERE landlord_id=?", (second["id"],)).fetchone()[0]
        if count == 0:
            conn.execute("""INSERT INTO properties
                (landlord_id,title,location,price,bedrooms,bathrooms,description,photo)
                VALUES (?,?,?,?,?,?,?,?)""",
                (second["id"], "Francistown starter home", "Francistown, Area W", 3200, 2, 1,
                 "A neat starter home in a convenient location.",
                 "https://images.unsplash.com/photo-1600047509807-ba8f99d2cdde?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1000&q=85"))
    if landlord and tenant:
        has_review = conn.execute("SELECT id FROM reviews WHERE landlord_id=? AND tenant_id=?",
                                  (landlord["id"], tenant["id"])).fetchone()
        if not has_review:
            conn.execute("INSERT INTO reviews (landlord_id,tenant_id,rating,comment) VALUES (?,?,?,?)",
                         (landlord["id"], tenant["id"], 5, "Great communication and a smooth viewing. Very helpful!"))
    conn.commit()

def seed_stays(conn):
    count = conn.execute("SELECT COUNT(*) FROM stays").fetchone()[0]
    if count > 0:
        return
    stays_data = [
        ("Airbnb","Modern studio in Gaborone CBD","Gaborone",650,"https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1556912173-3bb406ef7e77?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1484154218962-a197022b5858?auto=format&fit=crop&w=1000&q=85","Stylish studio with fast wifi and self check-in.","4.8","Great host, very clean. - Thabo"),
        ("Airbnb","Cosy 1-bedroom in Block 3","Gaborone",520,"https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1522771739844-6a9a0d0269b3?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1556911220-bff31c812dba?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1502005930093-1e9c02534a9b?auto=format&fit=crop&w=1000&q=85","Quiet apartment near shops.","4.6","Loved the location. - Naledi"),
        ("Airbnb","Family home in Broadhurst","Gaborone",1200,"https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600573472592-401b489a3cdc?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1000&q=85","Spacious family home with garden.","4.9","Perfect for family. - Kabelo"),
        ("Airbnb","Francistown city apartment","Francistown",480,"https://images.unsplash.com/photo-1600047509807-ba8f99d2cdde?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600585154526-990dced4db0d?auto=format&fit=crop&w=1000&q=85","Central apartment with parking.","4.5","Clean and convenient. - Mpho"),
        ("Airbnb","Maun safari lodge room","Maun",890,"https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1571896349842-33c89424de2d?auto=format&fit=crop&w=1000&q=85","Comfortable room near delta.","4.7","Amazing experience. - Sarah"),
        ("Airbnb","Kasane riverside cottage","Kasane",1100,"https://images.unsplash.com/photo-1582268611958-ebfd161ef9cf?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1000&q=85","Cottage with river views.","4.9","Stunning views. - John"),
        ("Airbnb","Palapye guest suite","Palapye",400,"https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1556912173-3bb406ef7e77?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1484154218962-a197022b5858?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1502005930093-1e9c02534a9b?auto=format&fit=crop&w=1000&q=85","Private suite with kitchenette.","4.4","Good value. - Lesego"),
        ("Airbnb","Molepolole village stay","Molepolole",350,"https://images.unsplash.com/photo-1564013799919-ab600027ffc6?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=1000&q=85","Traditional home experience.","4.3","Warm hosts. - Tumelo"),
        ("Airbnb","Lobatse hilltop villa","Lobatse",950,"https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1000&q=85","Villa with panoramic views.","4.8","Beautiful property. - Ana"),
        ("Airbnb","Serowe heritage home","Serowe",500,"https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1000&q=85","Heritage home with modern touches.","4.6","Unique stay. - David"),
        ("Guesthouse","Gaborone Sun Guesthouse","Gaborone",550,"https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?auto=format&fit=crop&w=1000&q=85","Comfortable guesthouse with breakfast.","4.5","Friendly staff. - Mimi"),
        ("Guesthouse","Francistown Inn","Francistown",420,"https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?auto=format&fit=crop&w=1000&q=85","Affordable inn in city center.","4.2","Good location. - Peter"),
        ("Guesthouse","Maun River Lodge","Maun",980,"https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?auto=format&fit=crop&w=1000&q=85","Lodge by the river with pool.","4.7","Lovely pool. - Lisa"),
        ("Guesthouse","Kasane Safari Inn","Kasane",870,"https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1000&q=85","Inn near Chobe National Park.","4.8","Great safari base. - Tom"),
        ("Guesthouse","Palapye Travellers Lodge","Palapye",380,"https://images.unsplash.com/photo-1571896349842-33c89424de2d?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?auto=format&fit=crop&w=1000&q=85","Budget lodge for travellers.","4.1","Clean rooms. - Grace"),
    ]
    for stype,title,loc,price,photo,desc,rating,rev in stays_data:
        conn.execute("""INSERT INTO stays (stay_type,title,location,price,photo,description,rating,reviews) VALUES (?,?,?,?,?,?,?,?)""",
                     (stype,title,loc,price,photo,desc,float(rating),rev))
    conn.commit()

def seed_houses(conn):
    count = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    if count >= 20:
        return
    landlord = conn.execute("SELECT id FROM users WHERE role='landlord' LIMIT 1").fetchone()
    lid = landlord["id"] if landlord else 1
    houses = [
        ("2-bedroom apartment in Gaborone Block 10","Gaborone, Block 10",5200,2,1,"Bright apartment near shops and transport.","https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1556912173-3bb406ef7e77?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1484154218962-a197022b5858?auto=format&fit=crop&w=1000&q=85"),
        ("Family home in Francistown Area W","Francistown, Area W",4800,3,2,"Spacious family home with fenced yard.","https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600573472592-401b489a3cdc?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1000&q=85"),
        ("Maun riverside apartment","Maun, Boseja",6000,2,1,"Apartment near the river with great views.","https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1522771739844-6a9a0d0269b3?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1556911220-bff31c812dba?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1502005930093-1e9c02534a9b?auto=format&fit=crop&w=1000&q=85"),
        ("Kasane family house with garden","Kasane, Plateau",7500,4,2,"Large family house with garden and garage.","https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566752355-35792bedcfea?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600573472592-401b489a3cdc?auto=format&fit=crop&w=1000&q=85"),
        ("Palapye starter home","Palapye, Extension 3",3200,2,1,"Neat starter home in quiet area.","https://images.unsplash.com/photo-1600047509807-ba8f99d2cdde?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600585154526-990dced4db0d?auto=format&fit=crop&w=1000&q=85"),
        ("Molepolole 3-bedroom home","Molepolole",4200,3,2,"Family home with carport and yard.","https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600573472592-401b489a3cdc?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1000&q=85"),
        ("Lobatse apartment","Lobatse",3800,2,1,"Apartment with balcony views.","https://images.unsplash.com/photo-1493809842364-78817add7cfa?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1540518614846-7eded433c457?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1505691938895-1758d7feb511?auto=format&fit=crop&w=1000&q=85"),
        ("Serowe family residence","Serowe",4000,3,2,"Large home with fenced yard.","https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1000&q=85"),
        ("Kanye two-bedroom home","Kanye",2800,2,1,"Affordable home in quiet neighbourhood.","https://images.unsplash.com/photo-1560184897-ae75f418493e?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1522771739844-6a9a0d0269b3?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1556911220-bff31c812dba?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1502005930093-1e9c02534a9b?auto=format&fit=crop&w=1000&q=85"),
        ("Mochudi modern home","Mochudi",3500,2,1,"Modern home with carport.","https://images.unsplash.com/photo-1564013799919-ab600027ffc6?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1613977257363-707ba9348227?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=1000&q=85"),
        ("Mahalapye townhouse","Mahalapye",3600,2,1,"Townhouse near main road.","https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600573472592-401b489a3cdc?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1000&q=85"),
        ("Selebi-Phikwe 3-bedroom","Selebi-Phikwe",3900,3,2,"Family home with garden.","https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566752355-35792bedcfea?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600573472592-401b489a3cdc?auto=format&fit=crop&w=1000&q=85"),
        ("Jwaneng 2-bedroom","Jwaneng",4100,2,1,"Home near the mine area.","https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1556912173-3bb406ef7e77?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1484154218962-a197022b5858?auto=format&fit=crop&w=1000&q=85"),
        ("Orapa family home","Orapa",4500,3,2,"Spacious home in Orapa.","https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600573472592-401b489a3cdc?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1000&q=85"),
        ("Tutume village home","Tutume",2600,2,1,"Affordable home in Tutume.","https://images.unsplash.com/photo-1600047509807-ba8f99d2cdde?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1000&q=85,https://images.unsplash.com/photo-1600585154526-990dced4db0d?auto=format&fit=crop&w=1000&q=85"),
    ]
    for title,loc,price,beds,baths,desc,photo in houses:
        exists = conn.execute("SELECT id FROM properties WHERE title=?",(title,)).fetchone()
        if exists:
            continue
        conn.execute("""INSERT INTO properties (landlord_id,title,location,price,bedrooms,bathrooms,description,photo,tenant_gender_pref,rent_share,bill_split,yard_size,parking,fencing,house_rules,preferred_tenant,electricity_meter,water_billing,water_amount,water_backup,deposit_terms,nearest_shop,shop_distance,combi_distance,road_type,landlord_notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (lid,title,loc,price,beds,baths,desc,photo,"Any","No","","Small plot","Open driveway","Wall","No subletting","Any","BPC Prepaid (Smarten/Hexing)","Individual WUC meter",None,0,"1 month deposit + 1st month rent","Choppies","500m (6 min walk)","300m","Tarmac","Well maintained property."))
    conn.commit()

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return user

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please log in first.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file):
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        raise ValueError("Use a JPG, PNG or WEBP image.")
    filename = secure_filename(file.filename)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    name = f"{stamp}_{filename}"
    file.save(os.path.join(UPLOAD_DIR, name))
    return name

BASE = r"""
<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MOAGI - Find your space</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#ffffff;color:#222222;font-family:"Segoe UI",Inter,system-ui,-apple-system,Roboto,Arial,sans-serif;font-size:16px;line-height:1.6}
a{color:inherit}nav{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:18px 6%;border-bottom:1px solid #ebebeb;position:sticky;top:0;background:#ffffff;z-index:10;flex-wrap:wrap;box-shadow:0 1px 2px rgba(0,0,0,.08)}
.logo{font-size:27px;font-weight:900;letter-spacing:2px;text-decoration:none;color:#222}nav .links{display:flex;gap:16px;align-items:center;flex-wrap:wrap}nav a{text-decoration:none;font-size:14px;color:#222}nav a:hover{color:#ff385c}
.container{width:90%;max-width:1120px;margin:32px auto}.hero{padding:55px 0 35px;animation:slideUp .65s ease both}.hero h1{font-size:clamp(32px,6vw,56px);letter-spacing:-1px;margin:8px 0;color:#222}.muted{color:#717171;line-height:1.6}.eyebrow{color:#717171;letter-spacing:3px;text-transform:uppercase;font-size:11px;font-weight:600}
.btn{display:inline-block;background:#222;color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:600;border:1px solid #222;cursor:pointer;transition:.15s}.btn:hover{background:#000;border-color:#000}.btn.ghost{background:#fff;color:#222;border-color:#b0b0b0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:18px}.card{background:#fff;border:1px solid #ebebeb;border-radius:12px;padding:18px;animation:slideUp .5s ease both;transition:transform .2s,box-shadow .2s;box-shadow:0 2px 8px rgba(0,0,0,.08)}.card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.12)}
.card img{width:100%;height:200px;object-fit:cover;border-radius:8px;background:#f7f7f7}.price{font-size:22px;font-weight:700;color:#222}.tag{font-size:12px;color:#222;border:1px solid #b0b0b0;padding:5px 9px;border-radius:20px;display:inline-block;background:#f7f7f7}
input,select,textarea{width:100%;padding:13px;margin:7px 0 15px;background:#fff;border:1px solid #b0b0b0;border-radius:8px;color:#222;font-size:15px}textarea{min-height:110px}label{font-size:13px;color:#222;font-weight:600}form{max-width:620px}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.flash{background:#f7f7f7;border:1px solid #ebebeb;border-radius:9px;padding:12px;margin:12px 0;color:#222}.profile-head{display:flex;gap:22px;align-items:center;flex-wrap:wrap}.avatar{width:112px;height:112px;border-radius:50%;object-fit:cover;background:#f7f7f7;border:2px solid #ebebeb}.review{padding:15px 0;border-bottom:1px solid #ebebeb}.stars{color:#ff385c;letter-spacing:2px}.message{background:#f7f7f7;border:1px solid #ebebeb;padding:12px 15px;border-radius:14px;margin:10px 0;max-width:78%;color:#222}.mine{margin-left:auto;background:#222;color:#fff}.small{font-size:12px;color:#717171}footer{text-align:center;padding:35px;color:#717171;border-top:1px solid #ebebeb;margin-top:40px}
#intro{position:fixed;inset:0;z-index:99;background:#ffffff;display:flex;align-items:center;justify-content:center;flex-direction:column;pointer-events:none;animation:introOut .9s ease 2.1s forwards}
#intro h1{font-size:clamp(48px,10vw,90px);margin:8px;animation:pop .8s ease both;color:#222}#intro p{color:#717171;letter-spacing:3px;animation:pop 1s ease .25s both}
#intro.hidden{display:none}@keyframes pop{from{opacity:0;transform:scale(.8)}to{opacity:1;transform:scale(1)}}@keyframes introOut{to{opacity:0;visibility:hidden}}@keyframes slideUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
@media(max-width:650px){nav{padding:15px 5%}.container{width:92%}.row{grid-template-columns:1fr}.hero{padding-top:35px}.message{max-width:92%}}
.ad-slideshow{position:relative;min-height:160px}.ad-slide{display:none;padding:20px;border:1px solid #ebebeb;border-radius:12px;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.08)}.ad-slide.active{display:block;animation:slideUp .5s ease both}

</style>
<style id="darkModeStyle" disabled>
body{background:#0b0d12;color:#f5f5f5}
nav{background:#11151b;border-color:#2a3040;box-shadow:none}
.logo,nav a{color:#f5f5f5}
.card{background:#161a22;border-color:#2a3040;box-shadow:0 2px 8px rgba(0,0,0,.4)}
.card img{background:#1f2430}
.muted{color:#a0a0a0}
.tag{background:#1f2430;border-color:#3a4050;color:#f5f5f5}
input,select,textarea{background:#1f2430;border-color:#3a4050;color:#f5f5f5}
.flash{background:#1f2430;border-color:#2a3040;color:#f5f5f5}
.avatar{background:#1f2430;border-color:#3a4050}
.review{border-color:#2a3040}
.message{background:#1f2430;border-color:#2a3040;color:#f5f5f5}
.mine{background:#2a3040;color:#fff}
.small{color:#a0a0a0}
footer{color:#a0a0a0;border-color:#2a3040}
.price{color:#f5f5f5}
.btn.ghost{background:#1f2430;color:#f5f5f5;border-color:#3a4050}
.hero h1{color:#f5f5f5}
#intro{background:#0b0d12}
#intro h1{color:#f5f5f5}
#intro p{color:#a0a0a0}
.ad-slide{background:#161a22;border-color:#2a3040}
.property-info,.landlord-panel{background:#161a22;border-color:#2a3040}
.property-spec{background:#1f2430;border-color:#3a4050;color:#f5f5f5}
.property-placeholder{background:linear-gradient(135deg,#1f2430,#161a22)}
.property-description{color:#d0d5dc}
.pay-method{background:#161a22;border-color:#2a3040}
</style>
</head><body>
<div id="intro"><h1>MOAGI.</h1><p>EITA DAH! </p></div>
<nav><a class="logo" href="/">MOAGI.</a><div class="links">
<a href="/houses">Houses</a><a href="/stays">Stays</a><button id="themeToggle" class="btn ghost" type="button" style="padding:8px 12px;font-size:13px">Dark</button>{% if me %}<a href="/dashboard">Dashboard</a><a href="/inbox">Inbox</a><a href="/profile/edit">My profile</a><a href="/logout">Log out</a>{% else %}<a href="/login">Log in</a><a class="btn" href="/register">Join MOAGI</a>{% endif %}
</div></nav><main class="container">
{% with items=get_flashed_messages() %}{% for item in items %}<div class="flash">{{item}}</div>{% endfor %}{% endwith %}
{{body|safe}}</main><footer>MOAGI - Find your space in Botswana</footer>
<script>
(function(){const intro=document.getElementById('intro');try{if(sessionStorage.getItem('moagi_welcomed')==='yes'){intro.classList.add('hidden')}else{sessionStorage.setItem('moagi_welcomed','yes')}}catch(e){}})();
(function(){var btn=document.getElementById('themeToggle');var style=document.getElementById('darkModeStyle');function apply(t){if(t==='dark'){style.disabled=false;btn.textContent='Light';document.body.setAttribute('data-theme','dark')}else{style.disabled=true;btn.textContent='Dark';document.body.setAttribute('data-theme','light')}}var saved=localStorage.getItem('moagi_theme')||'light';apply(saved);btn.addEventListener('click',function(){var next=(localStorage.getItem('moagi_theme')||'light')==='light'?'dark':'light';localStorage.setItem('moagi_theme',next);apply(next)});})();
</script></body></html>
"""

def page(template, **data):
    me = current_user()
    data.setdefault("me", me)
    body = render_template_string(template, **data)
    return render_template_string(BASE, body=body, me=me)

@app.route("/")
def home():
    return page("""
    <section class="hero"><div class="eyebrow">Botswana's home-finding space</div>
    <h1>Find a place<br>to call yours.</h1><p class="muted">Real homes. Real people. Your next chapter starts here.</p>
    <a class="btn" href="/register">Get started</a> <a class="btn ghost" href="/houses">Explore homes</a></section>

    <h2>Sections</h2>
    <div class="grid">
        <a class="card" href="/houses" style="text-decoration:none"><h3>Houses</h3><p class="muted">Browse and search rental homes across Botswana.</p></a>
        <a class="card" href="/inbox" style="text-decoration:none"><h3>Messages (DM)</h3><p class="muted">Private conversations with landlords and tenants.</p></a>
        <a class="card" href="/report" style="text-decoration:none"><h3>Reports</h3><p class="muted">Report a concern privately to MOAGI admins.</p></a>
        <a class="card" href="/stays" style="text-decoration:none"><h3>Stays (Airbnb & Guesthouses)</h3><p class="muted">Short-term stays, guesthouses and Airbnb across Botswana.</p></a>
        <a class="card" href="#help" style="text-decoration:none"><h3>Help</h3><p class="muted">How MOAGI works and how to get support.</p></a>
    </div>

    <h2>Ads</h2>
    <div class="ad-slideshow">
        <div class="ad-slide active">
            <img src="https://choppies.co.bw/wp-content/uploads/2024/05/SLIDER-chNew.jpg" alt="Choppies" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px" onerror="this.src='https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=800&q=80'">
            <h3>Choppies - Weekly Specials</h3>
            <p class="muted">Save big on groceries this week. Fresh produce, meat and household essentials at great prices.</p>
            <a class="btn" href="https://www.choppies.co.bw" target="_blank">Shop now</a>
        </div>
        <div class="ad-slide">
            <img src="https://spar.co.bw/wp-content/uploads/2026/09/Screenshot-2026-09-11-at-12.32.38.png" alt="Spar" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px" onerror="this.src='https://images.unsplash.com/photo-1578916171728-46686eac8d58?auto=format&fit=crop&w=800&q=80'">
            <h3>Spar Botswana - Fresh for Less</h3>
            <p class="muted">Quality groceries and fresh bakery items. Visit your nearest Spar today.</p>
            <a class="btn" href="https://www.spar.co.bw" target="_blank">Learn more</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1473341304170-971dccb5ac1e?auto=format&fit=crop&w=800&q=80" alt="BPC" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>Botswana Power Corporation</h3>
            <p class="muted">Pay your electricity bill online. Quick, safe and convenient.</p>
            <a class="btn" href="https://www.bpc.bw" target="_blank">Pay now</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=800&q=80" alt="Orange" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>Orange Botswana - More Data</h3>
            <p class="muted">Get more data for less. New prepaid bundles available now.</p>
            <a class="btn" href="https://www.orange.co.bw" target="_blank">See bundles</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=crop&w=800&q=80" alt="Mascom" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>Mascom - Network for Everyone</h3>
            <p class="muted">Reliable mobile and internet services across Botswana.</p>
            <a class="btn" href="https://www.mascom.bw" target="_blank">Explore</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=800&q=80" alt="Restaurant" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>Nandos Botswana - Flame Grilled</h3>
            <p class="muted">Peri-peri chicken and family meals. Dine in or takeaway.</p>
            <a class="btn" href="https://www.nandos.co.bw" target="_blank">Order now</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1563013544-824ae1b704d3?auto=format&fit=crop&w=800&q=80" alt="Bank" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>FNB Botswana - Easy Banking</h3>
            <p class="muted">Open an account online and bank from anywhere.</p>
            <a class="btn" href="https://www.fnb.co.bw" target="_blank">Open account</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1555396273-367ea4eb4db5?auto=format&fit=crop&w=800&q=80" alt="KFC" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>KFC Botswana - Finger Lickin Good</h3>
            <p class="muted">Fresh chicken meals and family buckets. Order online.</p>
            <a class="btn" href="https://www.kfc.co.bw" target="_blank">Order now</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1509042239860-f550ce710b93?auto=format&fit=crop&w=800&q=80" alt="Coffee" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>Vida e Caffe - Coffee & More</h3>
            <p class="muted">Fresh coffee, pastries and light meals.</p>
            <a class="btn" href="https://www.vidaecaffe.com" target="_blank">Visit</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1519999482648-25049ddd37b1?auto=format&fit=crop&w=800&q=80" alt="Bank" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>Standard Chartered Botswana</h3>
            <p class="muted">Banking made simple. Open an account today.</p>
            <a class="btn" href="https://www.sc.com/bw" target="_blank">Learn more</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1540553016722-983e48a2cd10?auto=format&fit=crop&w=800&q=80" alt="Woolworths" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>Woolworths Botswana - Quality Food</h3>
            <p class="muted">Fresh food, clothing and homeware.</p>
            <a class="btn" href="https://www.woolworths.co.bw" target="_blank">Shop</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1586880244386-869d68908f72?auto=format&fit=crop&w=800&q=80" alt="Pick n Pay" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>Pick n Pay Botswana - Save More</h3>
            <p class="muted">Weekly specials on groceries and household items.</p>
            <a class="btn" href="https://www.pnp.co.bw" target="_blank">View specials</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1558618666-fcd25c85cd64?auto=format&fit=crop&w=800&q=80" alt="Be Mobile" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>Be Mobile - Connect Botswana</h3>
            <p class="muted">Affordable mobile and data services.</p>
            <a class="btn" href="https://www.bemobile.bw" target="_blank">Explore</a>
        </div>
        <div class="ad-slide">
            <img src="https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?auto=format&fit=crop&w=800&q=80" alt="Game" style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px">
            <h3>Game Stores Botswana</h3>
            <p class="muted">Electronics, appliances and home goods.</p>
            <a class="btn" href="https://www.game.co.bw" target="_blank">Shop now</a>
        </div>
        <div class="ad-slide">
            <img 
src="https://choppies.co.bw/wp-content/uploads/2024/05/banners-2.jpg" alt="Choppies" 
style="width:100%;height:180px;object-fit:cover;border-radius:8px;margin-bottom:10px" onerror="this.src='https://images.unsplash.com/photo-1556742111-a301076d9d18?auto=format&fit=crop&w=800&q=80'">
            <h3>Choppies - More Savings</h3>
            <p class="muted">Extra discounts on selected items this week.</p>
            <a class="btn" href="https://www.choppies.co.bw" target="_blank">Shop now</a>
        </div>
    </div>
    <script>
    (function(){var s=document.querySelectorAll('.ad-slide');var i=0;setInterval(function(){s[i].classList.remove('active');i=(i+1)%s.length;s[i].classList.add('active');},4000);})();
    </script>

    <h2 id="help">Help</h2>
    <div class="card"><p class="muted">MOAGI connects landlords and tenants. Create an account, list or search homes, message landlords, and leave reviews. For support, contact the platform administrator.</p></div>
    """)

@app.route("/houses")
def houses():
    search = request.args.get("q", "").strip()
    location = request.args.get("location", "").strip()
    bedrooms = request.args.get("bedrooms", "").strip()
    conn = db()
    sql = """SELECT p.*,u.first_name,u.surname,u.profile_photo FROM properties p
             JOIN users u ON u.id=p.landlord_id WHERE 1=1"""
    args = []
    if search:
        sql += " AND (p.title LIKE ? OR p.location LIKE ? OR p.description LIKE ?)"
        args += [f"%{search}%"] * 3
    if location:
        sql += " AND p.location LIKE ?"
        args.append(f"%{location}%")
    if bedrooms.isdigit():
        sql += " AND p.bedrooms>=?"
        args.append(int(bedrooms))
    sql += " ORDER BY p.created_at DESC, p.id DESC"
    homes = conn.execute(sql, args).fetchall()
    conn.close()
    return page("""
    <h1>Houses</h1>
    <form method="get" class="card"><div class="row"><div><label>Search homes</label><input name="q" value="{{search}}" placeholder="Apartment, family home..."></div>
    <div><label>Town / location</label><input name="location" value="{{location}}" placeholder="Gaborone, Francistown..."></div></div>
    <label>Minimum bedrooms</label><select name="bedrooms"><option value="">Any</option>{% for n in range(1,7) %}<option value="{{n}}" {% if bedrooms==n|string %}selected{% endif %}>{{n}}+</option>{% endfor %}</select>
    <button class="btn">Find homes</button></form>
    <div class="grid">{% for p in homes %}
    <article class="card">{% if p.photo %}{% set _fp = p.photo.split(',')[0].strip() %}<img src="{{_fp if _fp.startswith('http') else url_for('static',filename='uploads/'+_fp)}}" alt="Property photo">{% else %}<div style="height:185px;background:#f7f7f7;border-radius:10px"></div>{% endif %}
    <p class="tag">{{p.location}}</p><h3>{{p.title}}</h3><div class="price">P{{"{:,.0f}".format(p.price)}} <span class="small">/ month</span></div>
    <p class="muted">{{p.bedrooms}} bedrooms, {{p.bathrooms}} bathrooms</p><p class="small">Listed by {{p.first_name}} {{p.surname}}</p><a class="btn" href="/property/{{p.id}}">View home</a></article>
    {% else %}<p class="muted">No homes match that search yet. Try another location.</p>{% endfor %}</div>
    """, homes=homes, search=search, location=location, bedrooms=bedrooms)

@app.route("/stays")
def stays():
    stype = request.args.get("type","").strip()
    conn = db()
    sql = "SELECT * FROM stays WHERE 1=1"
    args = []
    if stype:
        sql += " AND stay_type=?"
        args.append(stype)
    sql += " ORDER BY id DESC"
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return page("""
    <h1>Stays: Airbnb & Guesthouses</h1>
    <p class="muted">Short-term stays across Botswana. Book a room, guesthouse or Airbnb.</p>
    <div class="grid">{% for s in stays %}
    <article class="card">
        {% if s.photo %}{% set _fp = s.photo.split(',')[0].strip() %}<img src="{{_fp}}" alt="{{s.title}}">{% endif %}
        <p class="tag">{{s.stay_type}} - {{s.location}}</p>
        <h3>{{s.title}}</h3>
        <div class="price">P{{"{:,.0f}".format(s.price)}} <span class="small">/ night</span></div>
        <p class="muted">{{s.description}}</p>
        <p class="small">Rating: {{s.rating}}/5 - {{s.reviews}}</p>
        <a class="btn" href="/stay/{{s.id}}">View details</a> <a class="btn ghost" href="/pay?item={{s.title}}&amount={{s.price}}">Book & Pay</a>
    </article>
    {% else %}<p class="muted">No stays found.</p>{% endfor %}</div>
    """, stays=rows)

@app.route("/stay/<int:stay_id>")
def stay_detail(stay_id):
    conn = db()
    s = conn.execute("SELECT * FROM stays WHERE id=?",(stay_id,)).fetchone()
    conn.close()
    if not s: abort(404)
    return page("""
    <p><a href="/stays" class="muted">Back to stays</a></p>
    {% if s.photo %}{% for ph in s.photo.split(',') %}{% set ph = ph.strip() %}{% if ph %}<img src="{{ph}}" alt="{{s.title}}" style="width:100%;max-height:320px;object-fit:cover;border-radius:12px;margin-bottom:10px">{% endif %}{% endfor %}{% endif %}
    <div class="card">
        <p class="tag">{{s.stay_type}} - {{s.location}}</p>
        <h1>{{s.title}}</h1>
        <div class="price">P{{"{:,.0f}".format(s.price)}} <span class="small">/ night</span></div>
        <p class="muted">{{s.description}}</p>
        <p class="small">Rating: {{s.rating}}/5 - {{s.reviews}}</p>
        <h3>Book this stay</h3>
        <form method="get" action="/pay">
            <input type="hidden" name="item" value="{{s.title}}">
            <input type="hidden" name="amount" value="{{s.price}}">
            <div class="row">
                <div><label>Check-in date</label><input type="date" name="checkin" required></div>
                <div><label>Check-out date</label><input type="date" name="checkout" required></div>
            </div>
            <div class="row">
                <div><label>Check-in time</label><input type="time" name="checkin_time" value="14:00" required></div>
                <div><label>Check-out time</label><input type="time" name="checkout_time" value="10:00" required></div>
            </div>
            <label>Guests</label><input type="number" name="guests" min="1" value="1" required>
            <button class="btn" style="width:100%">Book & Pay</button>
        </form>
    </div>
    """, s=s)

@app.route("/pay", methods=["GET","POST"])
def pay():
    item = request.args.get("item","Booking")
    amount = request.args.get("amount","0")
    checkin = request.args.get("checkin","")
    checkout = request.args.get("checkout","")
    checkin_time = request.args.get("checkin_time","")
    checkout_time = request.args.get("checkout_time","")
    guests = request.args.get("guests","1")
    if request.method == "POST":
        method = request.form.get("method","")
        phone = request.form.get("phone","").strip()
        flash("Demo payment recorded via " + method + " for " + phone + ". (Live mobile-money API integration coming soon.)")
        return redirect(url_for("pay", item=item, amount=amount, checkin=checkin, checkout=checkout, checkin_time=checkin_time, checkout_time=checkout_time, guests=guests))
    return page("""
    <style>
    .pay-methods{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:15px 0}
    .pay-method{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:18px;border:2px solid #ebebeb;border-radius:12px;cursor:pointer;background:#fff;transition:.15s}
    .pay-method:hover{border-color:#222;transform:translateY(-2px)}
    .pay-method input{display:none}
    .pay-method.selected{border-color:#222;background:#f7f7f7}
    .pay-logo{font-size:26px;font-weight:800;margin-bottom:6px}
    .pay-myZaka{color:#00a651}
    .pay-orange{color:#ff6600}
    .pay-smega{color:#0033a0}
    </style>
    <h1>Pay for {{item}}</h1>
    <p class="muted">Amount: P{{amount}}. Choose a mobile money method.</p>
    {% if checkin %}
    <div class="card" style="margin-bottom:15px">
        <h3>Booking details</h3>
        <p class="muted">Check-in: {{checkin}} at {{checkin_time}}</p>
        <p class="muted">Check-out: {{checkout}} at {{checkout_time}}</p>
        <p class="muted">Guests: {{guests}}</p>
    </div>
    {% endif %}
    <form method="post" class="card" id="payForm">
        <input type="hidden" name="checkin" value="{{checkin}}">
        <input type="hidden" name="checkout" value="{{checkout}}">
        <input type="hidden" name="checkin_time" value="{{checkin_time}}">
        <input type="hidden" name="checkout_time" value="{{checkout_time}}">
        <input type="hidden" name="guests" value="{{guests}}">
        <div class="pay-methods">
            <label class="pay-method selected"><input type="radio" name="method" value="MyZaka" checked><img src="https://upload.wikimedia.org/wikipedia/commons/thumb/0/04/Mascom_logo.svg/120px-Mascom_logo.svg.png" alt="MyZaka" style="height:32px;object-fit:contain;margin-bottom:6px" onerror="this.style.display='none'"><span class="pay-logo pay-myZaka">MyZaka</span><span class="small">Mascom</span></label>
            <label class="pay-method"><input type="radio" name="method" value="Orange Money"><img src="https://upload.wikimedia.org/wikipedia/commons/thumb/c/c8/Orange_logo.svg/120px-Orange_logo.svg.png" alt="Orange Money" style="height:32px;object-fit:contain;margin-bottom:6px" onerror="this.style.display='none'"><span class="pay-logo pay-orange">Orange Money</span><span class="small">Orange</span></label>
            <label class="pay-method"><input type="radio" name="method" value="Smega"><img src="https://upload.wikimedia.org/wikipedia/en/thumb/9/9b/Botswana_Post_logo.png/120px-Botswana_Post_logo.png" alt="Smega" style="height:32px;object-fit:contain;margin-bottom:6px" onerror="this.style.display='none'"><span class="pay-logo pay-smega">Smega</span><span class="small">Botswana Post</span></label>
        </div>
        <label>Your phone number</label>
        <input name="phone" placeholder="+267 7X XXX XXX" required>
        <button class="btn" style="width:100%">Pay P{{amount}}</button>
    </form>
    <div class="card"><h3>Landlord onboarding</h3><p class="muted">Landlords pay a small onboarding fee via the same methods to activate listings.</p></div>
    <script>
    (function(){var labels=document.querySelectorAll('.pay-method');labels.forEach(function(l){l.addEventListener('click',function(){labels.forEach(function(x){x.classList.remove('selected')});l.classList.add('selected');});});})();
    </script>
    """, item=item, amount=amount, checkin=checkin, checkout=checkout, checkin_time=checkin_time, checkout_time=checkout_time, guests=guests)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        f = request.form
        first, last = f.get("first_name","").strip(), f.get("surname","").strip()
        email, phone = f.get("email","").strip().lower(), f.get("phone","").strip()
        password, role = f.get("password",""), f.get("role","")
        location = f.get("location","").strip()
        if not all([first,last,email,phone,password,location]) or role not in ("landlord","tenant"):
            flash("Please complete all required fields.")
        elif len(password) < 8:
            flash("Use a password with at least 8 characters.")
        else:
            conn = db()
            try:
                cur = conn.execute("""INSERT INTO users
                    (first_name,surname,email,phone,password,role,gender,citizenship,location,bio)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (first,last,email,phone,generate_password_hash(password),role,
                     f.get("gender",""),f.get("citizenship","Botswana"),location,""))
                conn.commit()
                session["user_id"] = cur.lastrowid
                conn.close()
                flash("Welcome to MOAGI!")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                conn.close()
                flash("That email is already registered. Please log in.")
    return page("""
    <h1>Create your MOAGI account.</h1><p class="muted">Join as a landlord or a tenant.</p>
    <form method="post"><div class="row"><div><label>First name</label><input name="first_name" required></div><div><label>Surname</label><input name="surname" required></div></div>
    <label>Email</label><input type="email" name="email" required><label>Phone (Botswana)</label><input name="phone" placeholder="+267..." required>
    <label>Password</label><input type="password" name="password" minlength="8" required>
    <label>I want to join as</label><select name="role"><option value="tenant">Tenant</option><option value="landlord">Landlord</option></select>
    <label>Town / location</label><input name="location" placeholder="Gaborone" required><label>Citizenship</label><input name="citizenship" value="Botswana">
    <label>Gender (optional)</label><select name="gender"><option value="">Prefer not to say</option><option>Female</option><option>Male</option><option>Other</option></select>
    <button class="btn">Create account</button></form><p class="muted">Already here? <a href="/login">Log in</a></p>
    """)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (request.form.get("email","").strip(),)).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], request.form.get("password","")):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.")
    return page("""
    <h1>Welcome back.</h1><form method="post"><label>Email</label><input type="email" name="email" required>
    <label>Password</label><input type="password" name="password" required><button class="btn">Log in</button></form>
    """)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))



@app.route("/dashboard")
@login_required
def dashboard():
    me = current_user()

    if me["role"] == "admin":
        return redirect(url_for("admin_dashboard"))

    conn = db()

    if me["role"] == "landlord":
        homes = conn.execute(
            "SELECT * FROM properties WHERE landlord_id=? ORDER BY id DESC",
            (me["id"],)
        ).fetchall()

        stats = conn.execute(
            "SELECT COUNT(*) n, COALESCE(AVG(rating),0) avg FROM reviews WHERE landlord_id=?",
            (me["id"],)
        ).fetchone()

    else:
        homes = conn.execute("""
            SELECT DISTINCT u.id,u.first_name,u.surname,u.profile_photo,u.location
            FROM users u
            JOIN reviews r ON r.landlord_id=u.id
            WHERE r.tenant_id=?
        """, (me["id"],)).fetchall()

        stats = None

    conn.close()

    if me["role"] == "landlord":
        return page("""
        <div class="eyebrow">Landlord dashboard</div>
        <h1>Hey, {{me.first_name}}.</h1>
        <p class="muted">Your space to manage listings and connect with tenants.</p>

        <div class="grid">
            <div class="card">
                <div class="price">{{homes|length}}</div>
                <p class="muted">Your active listings</p>
            </div>
            <div class="card">
                <div class="price">{{stats.n}}</div>
                <p class="muted">Tenant reviews: {{"%.1f"|format(stats.avg)}} / 5 stars</p>
            </div>
        </div>

        <p>
            <a class="btn" href="/add-property">+ Add a property</a>
            <a class="btn ghost" href="/landlord/{{me.id}}">View public profile</a>
        </p>

        <h2>Your listings</h2>
        <div class="grid">
            {% for p in homes %}
            <div class="card">
                <h3>{{p.title}}</h3>
                <p class="muted">{{p.location}}  P{{"{:,.0f}".format(p.price)}} / month</p>
                <a href="/property/{{p.id}}">Open listing</a>
            </div>
            {% else %}
            <p class="muted">You haven't listed a home yet.</p>
            {% endfor %}
        </div>
        """, me=me, homes=homes, stats=stats)

    return page("""
    <div class="eyebrow">Tenant dashboard</div>
    <h1>Hey, {{me.first_name}}.</h1>
    <p class="muted">Find a home, contact landlords and keep your conversations in one place.</p>
    <a class="btn" href="/">Explore homes</a>
    <a class="btn ghost" href="/inbox">Open inbox</a>

    <h2>Landlords you've reviewed</h2>
    {% for u in homes %}
    <div class="card">
        <a href="/landlord/{{u.id}}">{{u.first_name}} {{u.surname}}</a>
    </div>
    {% else %}
    <p class="muted">Your reviewed landlords will appear here.</p>
    {% endfor %}
    """, me=me, homes=homes)


@app.route("/profile/edit", methods=["GET","POST"])
@login_required
def edit_profile():
    me = current_user()
    if request.method == "POST":
        try:
            photo = save_image(request.files.get("profile_photo"))
        except ValueError as e:
            flash(str(e)); return redirect(url_for("edit_profile"))
        conn = db()
        if photo:
            conn.execute("UPDATE users SET bio=?,location=?,profile_photo=? WHERE id=?",
                         (request.form.get("bio","").strip(),request.form.get("location","").strip(),photo,me["id"]))
        else:
            conn.execute("UPDATE users SET bio=?,location=? WHERE id=?",
                         (request.form.get("bio","").strip(),request.form.get("location","").strip(),me["id"]))
        conn.commit(); conn.close()
        flash("Your profile has been updated.")
        return redirect(url_for("landlord_profile", user_id=me["id"]))
    return page("""
    <h1>Edit your profile</h1><form method="post" enctype="multipart/form-data">
    <label>Profile picture (JPG, PNG or WEBP; max 5MB)</label><input type="file" name="profile_photo" accept=".jpg,.jpeg,.png,.webp">
    <label>Town / location</label><input name="location" value="{{me.location or ''}}" required>
    <label>About you</label><textarea name="bio" placeholder="Tell people a little about yourself...">{{me.bio or ''}}</textarea>
    <button class="btn">Save profile</button></form>
    """, me=me)

@app.route("/landlord/<int:user_id>")
def landlord_profile(user_id):
    conn = db()
    landlord = conn.execute("SELECT * FROM users WHERE id=? AND role='landlord'",(user_id,)).fetchone()
    if not landlord:
        conn.close(); abort(404)
    homes = conn.execute("SELECT * FROM properties WHERE landlord_id=? ORDER BY id DESC",(user_id,)).fetchall()
    reviews = conn.execute("""SELECT r.*,u.first_name,u.surname FROM reviews r
        JOIN users u ON u.id=r.tenant_id WHERE r.landlord_id=? ORDER BY r.created_at DESC""",(user_id,)).fetchall()
    avg = conn.execute("SELECT COALESCE(AVG(rating),0) FROM reviews WHERE landlord_id=?",(user_id,)).fetchone()[0]
    count = len(reviews)
    report_count = conn.execute("SELECT COUNT(*) FROM reports WHERE reported_user_id=?",(user_id,)).fetchone()[0]
    conn.close()
    return page("""
    <div class="profile-head">{% if landlord.profile_photo %}<img class="avatar" src="{{landlord.profile_photo if landlord.profile_photo.startswith('http') else url_for('static',filename='uploads/'+landlord.profile_photo)}}">{% else %}<div class="avatar"></div>{% endif %}
    <div><div class="eyebrow">Landlord profile</div><h1>{{landlord.first_name}} {{landlord.surname}}</h1><p class="muted">{{landlord.location}}  {{'' * (avg|round|int)}}{{'' * (5-(avg|round|int))}} {{'%.1f'|format(avg)}}/5 ({{count}} reviews)</p></div></div>
    <p class="muted">{{landlord.bio or 'This landlord has not added a bio yet.'}}</p>
    {% if landlord.deposit_refund_days %}<p class="muted"><b>Avg. deposit refund:</b> {{landlord.deposit_refund_days}} days</p>{% endif %}
    {% if landlord.response_rate %}<p class="muted"><b>Response rate:</b> {{landlord.response_rate}}%</p>{% endif %}
    {% if report_count and report_count > 0 %}<div class="flash">This landlord has {{report_count}} report(s) submitted by tenants. Review carefully before proceeding.</div>{% endif %}
    {% if me and me.id != landlord.id %}<a class="btn" href="/chat/{{landlord.id}}">Message landlord</a>{% endif %}
    <h2>Properties</h2><div class="grid">{% for p in homes %}<div class="card"><h3>{{p.title}}</h3><p class="muted">{{p.location}}  P{{"{:,.0f}".format(p.price)}} / month</p><a href="/property/{{p.id}}">View property</a></div>{% else %}<p class="muted">No properties listed yet.</p>{% endfor %}</div>
    <hr><h2>Tenant reviews & comments</h2>{% if me and me.role=='tenant' and me.id != landlord.id %}
    <form method="post" action="/review/{{landlord.id}}" class="card"><label>Your rating</label><select name="rating" required><option value="5">  Excellent</option><option value="4">  Good</option><option value="3">  Okay</option><option value="2">  Poor</option><option value="1">  Very poor</option></select><label>Your comment</label><textarea name="comment" maxlength="1000" required placeholder="Share your experience..."></textarea><button class="btn">Post review</button></form>
    {% elif not me %}<p class="muted"><a href="/login">Log in as a tenant</a> to leave a review.</p>{% endif %}
    {% for r in reviews %}<div class="review"><div class="stars">{{'' * r.rating}}{{'' * (5-r.rating)}}</div><b>{{r.first_name}} {{r.surname}}</b><p class="muted">{{r.comment}}</p><span class="small">{{r.created_at}}</span></div>{% else %}<p class="muted">No reviews yet.</p>{% endfor %}
    """, landlord=landlord, homes=homes, reviews=reviews, avg=avg, count=count, report_count=report_count)

@app.route("/review/<int:landlord_id>", methods=["POST"])
@login_required
def add_review(landlord_id):
    me = current_user()
    if me["role"] != "tenant" or me["id"] == landlord_id:
        abort(403)
    try:
        rating = int(request.form.get("rating","0"))
    except ValueError:
        rating = 0
    comment = request.form.get("comment","").strip()
    if rating not in range(1,6) or not comment:
        flash("Choose a rating and write a comment.")
    else:
        conn = db()
        landlord = conn.execute("SELECT id FROM users WHERE id=? AND role='landlord'",(landlord_id,)).fetchone()
        if not landlord:
            conn.close(); abort(404)
        conn.execute("""INSERT INTO reviews (landlord_id,tenant_id,rating,comment) VALUES (?,?,?,?)
            ON CONFLICT(landlord_id,tenant_id) DO UPDATE SET rating=excluded.rating,comment=excluded.comment,created_at=CURRENT_TIMESTAMP""",
            (landlord_id,me["id"],rating,comment))
        conn.commit(); conn.close()
        flash("Thanks! Your review has been posted.")
    return redirect(url_for("landlord_profile",user_id=landlord_id))

@app.route("/add-property", methods=["GET","POST"])
@login_required
def add_property():
    me = current_user()
    if me["role"] != "landlord":
        abort(403)
    if request.method == "POST":
        f = request.form
        try:
            price = float(f.get("price","0")); beds = int(f.get("bedrooms","0")); baths = int(f.get("bathrooms","0"))
            photos = []
            for upload in request.files.getlist("photo")[:10]:
                name = save_image(upload)
                if name:
                    photos.append(name)
            photo = ",".join(photos) if photos else None
        except (ValueError, TypeError) as e:
            flash(str(e) or "Check the price and room numbers."); return redirect(url_for("add_property"))
        title, location, description = f.get("title","").strip(), f.get("location","").strip(), f.get("description","").strip()
        if not title or not location or not description or price <= 0 or beds < 0 or baths < 0:
            flash("Please complete all property details with a valid rent amount.")
        else:
            conn = db()
            tgp = f.get("tenant_gender_pref","Any")
            rs = f.get("rent_share","No")
            bs = f.get("bill_split","").strip()
            yard = f.get("yard_size","").strip()
            parking = f.get("parking","").strip()
            fencing = f.get("fencing","").strip()
            rules = f.get("house_rules","").strip()
            pref = f.get("preferred_tenant","").strip()
            emeter = f.get("electricity_meter","").strip()
            wbilling = f.get("water_billing","").strip()
            wamount = f.get("water_amount","").strip()
            wbackup = 1 if f.get("water_backup") else 0
            dterms = f.get("deposit_terms","").strip()
            nshop = f.get("nearest_shop","").strip()
            sdist = f.get("shop_distance","").strip()
            cdist = f.get("combi_distance","").strip()
            rtype = f.get("road_type","").strip()
            lnotes = f.get("landlord_notes","").strip()
            try:
                wamount = float(wamount) if wamount else None
            except ValueError:
                wamount = None
            conn.execute("""INSERT INTO properties (landlord_id,title,location,price,bedrooms,bathrooms,description,photo,tenant_gender_pref,rent_share,bill_split,yard_size,parking,fencing,house_rules,preferred_tenant,electricity_meter,water_billing,water_amount,water_backup,deposit_terms,nearest_shop,shop_distance,combi_distance,road_type,landlord_notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(me["id"],title,location,price,beds,baths,description,photo,tgp,rs,bs,yard,parking,fencing,rules,pref,emeter,wbilling,wamount,wbackup,dterms,nshop,sdist,cdist,rtype,lnotes))
            conn.commit(); conn.close()
            flash("Your property is now listed.")
            return redirect(url_for("dashboard"))
    return page("""
    <h1>List a property</h1><form method="post" enctype="multipart/form-data">
    <label>Property title</label><input name="title" required placeholder="Modern 2-bedroom apartment">
    <label>Town / area</label><input name="location" required placeholder="Gaborone, Block 8">
    <div class="row"><div><label>Monthly rent (BWP)</label><input type="number" name="price" min="1" step="1" required></div><div><label>Bedrooms</label><input type="number" name="bedrooms" min="0" required></div></div>
    <label>Bathrooms</label><input type="number" name="bathrooms" min="0" required>
    <label>Description</label><textarea name="description" required></textarea>
    <label>Property photos (optional; JPG, PNG or WEBP; select up to 10 from your gallery)</label><input type="file" name="photo" accept=".jpg,.jpeg,.png,.webp" multiple>
    <label>Preferred tenant gender</label><select name="tenant_gender_pref"><option>Any</option><option>Female only</option><option>Male only</option></select>
    <label>Looking to share rent?</label><select name="rent_share"><option>No</option><option>Yes - room available</option></select>
    <label>Bill splitting details (if sharing)</label><textarea name="bill_split" placeholder="e.g. Split electricity and water equally; rent P2500 each"></textarea>
    <h3>Yard & Outdoor</h3>
    <label>Yard size</label><select name="yard_size"><option>Small plot</option><option>Paved yard</option><option>Large grassy yard</option><option>No yard</option></select>
    <label>Fencing</label><select name="fencing"><option>Wall</option><option>Electric fence</option><option>Mesh</option><option>None</option></select>
    <label>Parking</label><input name="parking" placeholder="e.g. Covered carport, 2 bays">
    <label>House rules</label><textarea name="house_rules" placeholder="Visitor policy, noise, subletting, maintenance..."></textarea>
    <label>Preferred tenant type</label><select name="preferred_tenant"><option>Any</option><option>Singles</option><option>Families</option><option>Working professionals</option><option>Students</option></select>
    <h3>Utilities (Botswana)</h3>
    <label>Electricity meter type</label><select name="electricity_meter"><option>BPC Prepaid (Smarten/Hexing)</option><option>Orange token meter</option><option>Post-paid BPC</option><option>Shared meter</option></select>
    <label>Water billing</label><select name="water_billing"><option>Individual WUC meter</option><option>Fixed monthly fee</option><option>Shared split</option><option>Included in rent</option><option>Borehole</option></select>
    <label>Water fixed amount (BWP)</label><input type="number" name="water_amount" min="0" step="1">
    <label><input type="checkbox" name="water_backup" value="1"> Water backup tank (Jojo) available</label>
    <label>Deposit terms</label><input name="deposit_terms" placeholder="e.g. 1 month deposit + 1st month rent">
    <h3>Neighbourhood & Convenience</h3>
    <label>Nearest supermarket</label><select name="nearest_shop"><option>Choppies</option><option>Pick n Pay</option><option>Spar</option><option>Sefalana</option><option>Shoprite</option></select>
    <label>Distance to supermarket</label><input name="shop_distance" placeholder="e.g. 400m (5 min walk)">
    <label>Distance to combi stop</label><input name="combi_distance" placeholder="e.g. 200m">
    <label>Road type</label><select name="road_type"><option>Tarmac</option><option>Paved</option><option>Dirt/Gravel</option></select>
    <label>Landlord notes / comments on this property</label><textarea name="landlord_notes" placeholder="Extra details, highlights, neighbourhood comments..."></textarea>
    <button class="btn">Publish listing</button></form>
    """)

@app.route("/property/<int:property_id>")
def property_detail(property_id):
    conn = db()
    p = conn.execute("""SELECT p.*,u.first_name,u.surname,u.id landlord_user_id,u.location landlord_location
        FROM properties p JOIN users u ON u.id=p.landlord_id WHERE p.id=?""",(property_id,)).fetchone()
    comments = conn.execute("""SELECT c.*,u.first_name,u.surname,u.role FROM listing_comments c
        JOIN users u ON u.id=c.author_id WHERE c.property_id=? ORDER BY c.created_at ASC""",(property_id,)).fetchall()
    conn.close()
    if not p: abort(404)
    return page("""
    <style>
    .property-layout {
        display:grid;
        grid-template-columns:1.5fr 1fr;
        gap:25px;
        align-items:start;
    }
    .property-photo {
        width:100%;
        height:390px;
        object-fit:cover;
        border-radius:16px;
        background:#f7f7f7;
        display:block;
    }
    .property-placeholder {
        height:390px;
        border-radius:16px;
        background:linear-gradient(135deg,#f7f7f7,#ffffff);
        display:flex;
        align-items:center;
        justify-content:center;
        color:#717171;
    }
    .property-info {
        background:#ffffff;
        border:1px solid #ebebeb;
        border-radius:18px;
        padding:25px;
    }
    .property-price {
        font-size:32px;
        font-weight:800;
        color:#222222;
        margin:15px 0;
    }
    .property-specs {
        display:flex;
        flex-wrap:wrap;
        gap:10px;
        margin:20px 0;
    }
    .property-spec {
        background:#f7f7f7;
        border:1px solid #b0b0b0;
        padding:12px 15px;
        border-radius:10px;
        color:#222222;
    }
    .property-description {
        white-space:pre-line;
        line-height:1.8;
        color:#222222;
    }
    .landlord-panel {
        margin-top:22px;
        padding:20px;
        background:#ffffff;
        border:1px solid #ebebeb;
        border-radius:16px;
    }
    .property-actions {
        display:flex;
        flex-wrap:wrap;
        gap:10px;
        margin-top:20px;
    }
    @media(max-width:750px) {
        .property-layout {grid-template-columns:1fr}
        .property-photo,.property-placeholder {height:260px}
        .property-info {padding:19px}
        .property-price {font-size:27px}
    }
    </style>

    <p><a href="/" class="muted">Back to explore homes</a></p>

    <div class="property-layout">
        <section>
            {% if p.photo %}
                {% for ph in p.photo.split(',') %}
                    {% set ph = ph.strip() %}
                    {% if ph %}
                        <img class="property-photo"
                        src="{{ph if ph.startswith('http') else url_for('static',filename='uploads/'+ph)}}"
                        alt="{{p.title}} - room {{loop.index}}" style="margin-bottom:14px">
                    {% endif %}
                {% endfor %}
            {% else %}
                <div class="property-placeholder">Property photo unavailable</div>
            {% endif %}

            <div class="property-info" style="margin-top:20px">
                <span class="tag">{{p.location}}</span>
                <h1>{{p.title}}</h1>

                <div class="property-price">
                    P{{"{:,.0f}".format(p.price)}}
                    <span class="small">/ month</span>
                </div>

                <div class="property-specs">
                    <div class="property-spec">{{p.bedrooms}} Bedrooms</div>
                    <div class="property-spec">{{p.bathrooms}} Bathrooms</div>
                    <div class="property-spec">Tenant: {{p.tenant_gender_pref or 'Any'}}</div>
                    {% if p.rent_share and p.rent_share.startswith('Yes') %}
                    <div class="property-spec">Rent sharing available</div>
                    {% endif %}
                </div>
                {% if p.bill_split %}
                <p class="muted"><b>Bill split:</b> {{p.bill_split}}</p>
                {% endif %}
                <div class="card" style="margin-top:15px">
                    <h3>Property highlights</h3>
                    <p class="muted"><b>Yard:</b> {{p.yard_size or 'Not specified'}} | <b>Fencing:</b> {{p.fencing or 'Not specified'}} | <b>Parking:</b> {{p.parking or 'Not specified'}}</p>
                    <p class="muted"><b>Preferred tenant:</b> {{p.preferred_tenant or 'Any'}}</p>
                    <p class="muted"><b>House rules:</b> {{p.house_rules or 'Not specified'}}</p>
                    <p class="muted"><b>Electricity:</b> {{p.electricity_meter or 'Not specified'}}</p>
                    <p class="muted"><b>Water:</b> {{p.water_billing or 'Not specified'}}{% if p.water_amount %} (P{{p.water_amount}}){% endif %}{% if p.water_backup %} | Backup tank available{% endif %}</p>
                    <p class="muted"><b>Deposit terms:</b> {{p.deposit_terms or 'Not specified'}}</p>
                </div>
                <div class="card" style="margin-top:15px">
                    <h3>Neighbourhood & Convenience</h3>
                    <p class="muted"><b>Nearest shop:</b> {{p.nearest_shop or 'Not specified'}} ({{p.shop_distance or 'Not specified'}})</p>
                    <p class="muted"><b>Combi stop:</b> {{p.combi_distance or 'Not specified'}}</p>
                    <p class="muted"><b>Road type:</b> {{p.road_type or 'Not specified'}}</p>
                </div>
                {% if p.landlord_notes %}
                <div class="card" style="margin-top:15px">
                    <h3>Landlord notes</h3>
                    <p class="muted">{{p.landlord_notes}}</p>
                </div>
                {% endif %}

                <hr style="border:0;border-top:1px solid #ebebeb">
                <h2>About this property</h2>
                <div class="property-description">{{p.description or "No property description has been added yet."}}</div>

                <h2>Questions & Comments</h2>
                {% for c in comments %}
                <div class="review">
                    <b>{{c.first_name}} {{c.surname}}{% if c.is_landlord_reply %} (Landlord){% endif %}</b>
                    <p class="muted">{{c.content}}</p>
                    <span class="small">{{c.created_at}}</span>
                </div>
                {% else %}
                <p class="muted">No questions yet. Be the first to ask.</p>
                {% endfor %}
                {% if me %}
                <form method="post" action="/property/{{p.id}}/comment" class="card">
                    <label>Ask a question or comment</label>
                    <textarea name="content" required placeholder="Is the yard fenced? Is pet allowed?"></textarea>
                    <button class="btn">Post</button>
                </form>
                {% else %}
                <p class="muted"><a href="/login">Log in</a> to ask a question.</p>
                {% endif %}
            </div>
        </section>

        <aside>
            <div class="property-info">
                <div class="eyebrow">Interested in this home?</div>
                <h2>Make your next move.</h2>
                <p class="muted">Connect directly with the landlord to ask questions and discuss this property.</p>

                <div class="property-actions">
                    {% if me and me.id != p.landlord_id %}
                        <a class="btn" href="/chat/{{p.landlord_id}}?property_id={{p.id}}">Contact landlord</a>
                    {% elif not me %}
                        <a class="btn" href="/login">Log in to contact landlord</a>
                    {% else %}
                        <p class="muted">This is your property listing.</p>
                    {% endif %}
                    <a class="btn ghost" href="/">Browse more homes</a>
                </div>
            </div>

            <div class="landlord-panel">
                <div class="eyebrow">Listed by</div>
                <h2>{{p.first_name}} {{p.surname}}</h2>
                <p class="muted">{{p.landlord_location}}</p>
                <a href="/landlord/{{p.landlord_id}}">View landlord profile</a>
            </div>
        </aside>
    </div>
    """, p=p, comments=comments)

@app.route("/property/<int:property_id>/comment", methods=["POST"])
@login_required
def add_listing_comment(property_id):
    me = current_user()
    content = request.form.get("content","").strip()
    if not content:
        flash("Comment cannot be empty.")
        return redirect(url_for("property_detail", property_id=property_id))
    conn = db()
    p = conn.execute("SELECT landlord_id FROM properties WHERE id=?",(property_id,)).fetchone()
    if not p:
        conn.close(); abort(404)
    is_reply = 1 if me["id"] == p["landlord_id"] else 0
    conn.execute("INSERT INTO listing_comments (property_id,author_id,content,is_landlord_reply) VALUES (?,?,?,?)",
                (property_id, me["id"], content[:1000], is_reply))
    conn.commit(); conn.close()
    flash("Your comment has been posted.")
    return redirect(url_for("property_detail", property_id=property_id))

@app.route("/inbox")
@login_required
def inbox():
    me = current_user()
    conn = db()

    rows = conn.execute("""
        SELECT m.*,
               u.first_name, u.surname, u.profile_photo
        FROM messages m
        JOIN users u ON u.id =
            CASE WHEN m.sender_id=? THEN m.recipient_id
                 ELSE m.sender_id END
        WHERE m.sender_id=? OR m.recipient_id=?
        ORDER BY m.created_at DESC, m.id DESC
    """, (me["id"], me["id"], me["id"])).fetchall()

    conn.close()
    seen, chats = set(), []

    for r in rows:
        other = r["recipient_id"] if r["sender_id"] == me["id"] else r["sender_id"]
        if other not in seen:
            seen.add(other)
            chats.append({
                "id": other,
                "name": r["first_name"] + " " + r["surname"],
                "photo": r["profile_photo"],
                "message": r["message"],
                "date": r["created_at"]
            })

    return page("""
    <style>
    .dm-heading{font-size:28px;margin-bottom:6px}
    .dm-card{display:flex;align-items:center;gap:15px;padding:17px;
        border:1px solid #303030;border-radius:18px;margin:12px 0;
        background:#151515;color:white;text-decoration:none;
        transition:.2s}
    .dm-card:hover{background:#222;transform:translateY(-2px)}
    .dm-avatar{width:52px;height:52px;min-width:52px;
        border-radius:50%;object-fit:cover;background:#333;
        display:flex;align-items:center;justify-content:center;
        font-weight:bold;font-size:18px}
    .dm-preview{color:#aaa;margin:5px 0 0;overflow:hidden;
        text-overflow:ellipsis;white-space:nowrap}
    .dm-date{font-size:12px;color:#999;white-space:nowrap}
    </style>

    <h1 class="dm-heading">Your inbox</h1>
    <p class="muted">Your private MOAGI conversations.</p>

    {% for c in chats %}
    <a class="dm-card" href="/chat/{{c.id}}">
        {% if c.photo %}
            <img class="dm-avatar"
            src="{{c.photo if c.photo.startswith('http') else url_for('static',filename='uploads/'+c.photo)}}">
        {% else %}
            <div class="dm-avatar">{{c.name[:1]|upper}}</div>
        {% endif %}

        <div style="flex:1;min-width:0">
            <b>{{c.name}}</b>
            <p class="dm-preview">{{c.message}}</p>
        </div>
        <span class="dm-date">{{c.date}}</span>
    </a>
    {% else %}
        <div class="card">
            <h3> No conversations yet</h3>
            <p class="muted">Explore properties and say hello to a landlord.</p>
            <a class="btn" href="/">Explore homes</a>
        </div>
    {% endfor %}
    """, chats=chats)


@app.route("/chat/<int:other_id>", methods=["GET","POST"])
@login_required
def chat(other_id):
    me = current_user()

    if other_id == me["id"]:
        abort(400)

    conn = db()
    other = conn.execute(
        "SELECT * FROM users WHERE id=?", (other_id,)
    ).fetchone()

    if not other:
        conn.close()
        abort(404)

    if request.method == "POST":
        message = request.form.get("message", "").strip()

        if message:
            conn.execute("""
                INSERT INTO messages
                (sender_id,recipient_id,property_id,message)
                VALUES (?,?,?,?)
            """, (
                me["id"],
                other_id,
                int(request.args.get("property_id", 0) or 0),
                message[:3000]
            ))
            conn.commit()

        conn.close()
        return redirect(url_for("chat", other_id=other_id))

    messages = conn.execute("""
        SELECT m.*, u.first_name AS sender_first_name,
               u.surname AS sender_surname,
               u.profile_photo AS sender_photo
        FROM messages m
        JOIN users u ON u.id=m.sender_id
        WHERE
        (m.sender_id=? AND m.recipient_id=?)
        OR
        (m.sender_id=? AND m.recipient_id=?)
        ORDER BY m.created_at ASC, m.id ASC
    """, (me["id"], other_id, other_id, me["id"])).fetchall()

    conn.close()

    return page("""
    <style>
    .chat-header{display:flex;align-items:center;gap:13px;
        padding:15px;background:#151515;border-radius:18px;
        border:1px solid #303030;margin-bottom:18px}
    .chat-avatar{width:46px;height:46px;min-width:46px;
        border-radius:50%;object-fit:cover;background:#333;
        display:flex;align-items:center;justify-content:center;
        font-weight:bold;font-size:18px}
    .chat-feed{display:flex;flex-direction:column;gap:17px;
        padding:12px 0}
    .chat-line{display:flex;align-items:flex-end;gap:10px;
        max-width:88%}
    .chat-line.mine{align-self:flex-end;flex-direction:row-reverse}
    .chat-bubble{padding:12px 15px;border-radius:18px;
        background:#252525;color:white;overflow-wrap:anywhere;
        border:1px solid #383838}
    .chat-line.mine .chat-bubble{background:#174b83;
        border-color:#2866a5}
    .chat-sender{font-size:12px;font-weight:bold;color:#ccc;
        margin-bottom:5px}
    .chat-time{font-size:11px;color:#bbb;margin-top:7px}
    .chat-composer{position:sticky;bottom:0;background:#101010;
        padding:13px 0 5px}
    .emoji-row{display:flex;gap:9px;margin-bottom:10px;
        flex-wrap:wrap}
    .emoji-button{background:#252525;border:1px solid #444;
        border-radius:20px;padding:7px 11px;color:white;
        cursor:pointer;font-size:17px}
    .emoji-button:hover{background:#444}
    .chat-input{width:100%;box-sizing:border-box;
        border-radius:16px;min-height:65px}
    </style>

    <h1>Messages</h1>

    <div class="chat-header">
        {% if other.profile_photo %}
            <img class="chat-avatar"
            src="{{other.profile_photo if other.profile_photo.startswith('http') else url_for('static',filename='uploads/'+other.profile_photo)}}">
        {% else %}
            <div class="chat-avatar">{{other.first_name[:1]|upper}}</div>
        {% endif %}
        <div>
            <b>{{other.first_name}} {{other.surname}}</b>
            <p class="muted" style="margin:4px 0">MOAGI member - Private conversation</p>
        </div>
    </div>

    <div class="chat-feed">
        {% for m in messages %}
        <div class="chat-line {% if m.sender_id==me.id %}mine{% endif %}">
            {% if m.sender_photo %}
                <img class="chat-avatar"
                src="{{m.sender_photo if m.sender_photo.startswith('http') else url_for('static',filename='uploads/'+m.sender_photo)}}">
            {% else %}
                <div class="chat-avatar">{{m.sender_first_name[:1]|upper}}</div>
            {% endif %}

            <div class="chat-bubble">
                <div class="chat-sender">
                    {% if m.sender_id==me.id %}You{% else %}{{m.sender_first_name}}{% endif %}
                </div>
                <div>{{m.message}}</div>
                <div class="chat-time">{{m.created_at}}</div>
            </div>
        </div>
        {% else %}
            <p class="muted"> Say hello and start the conversation!</p>
        {% endfor %}
    </div>

    <div class="chat-composer">
        <div class="emoji-row">
            <button type="button" class="emoji-button" onclick="addEmoji('')"></button>
            <button type="button" class="emoji-button" onclick="addEmoji('')"></button>
            <button type="button" class="emoji-button" onclick="addEmoji('')"></button>
            <button type="button" class="emoji-button" onclick="addEmoji('')"></button>
            <button type="button" class="emoji-button" onclick="addEmoji('')"></button>
            <button type="button" class="emoji-button" onclick="addEmoji('')"></button>
            <button type="button" class="emoji-button" onclick="addEmoji('')"></button>
        </div>

        <form method="post">
            <textarea id="chatMessage" class="chat-input"
                name="message" placeholder="Write your message... "
                required maxlength="3000"></textarea>
            <button class="btn" style="width:100%;margin-top:9px">
                Send message
            </button>
        </form>
    </div>

    <script>
    function addEmoji(emoji) {
        const input = document.getElementById("chatMessage");
        input.value += emoji;
        input.focus();
    }
    </script>
    """, other=other, messages=messages)

@app.route("/report", methods=["GET", "POST"])
@login_required
def report():
    me = current_user()

    if request.method == "POST":
        report_type = request.form.get("report_type", "").strip()
        category = request.form.get("category", "").strip()
        details = request.form.get("details", "").strip()
        reported_user_id = request.form.get("reported_user_id", "").strip()
        property_id = request.form.get("property_id", "").strip()

        if report_type not in ("landlord", "tenant", "property"):
            flash("Please select a valid report type.")
            return redirect(url_for("report"))

        if not category or len(details) < 10:
            flash("Please select a category and provide at least 10 characters of detail.")
            return redirect(url_for("report"))

        reported_id = None
        property_ref = None

        conn = db()

        if report_type in ("landlord", "tenant"):
            if not reported_user_id.isdigit():
                conn.close()
                flash("Please provide a valid account ID.")
                return redirect(url_for("report"))

            reported_id = int(reported_user_id)
            target = conn.execute(
                "SELECT id, role FROM users WHERE id=?",
                (reported_id,)
            ).fetchone()

            if not target or target["role"] != report_type or reported_id == me["id"]:
                conn.close()
                flash("That account cannot be reported using this selection.")
                return redirect(url_for("report"))

        if report_type == "property":
            if not property_id.isdigit():
                conn.close()
                flash("Please provide a valid property ID.")
                return redirect(url_for("report"))

            property_ref = int(property_id)
            target = conn.execute(
                "SELECT id, landlord_id FROM properties WHERE id=?",
                (property_ref,)
            ).fetchone()

            if not target:
                conn.close()
                flash("That property could not be found.")
                return redirect(url_for("report"))

            reported_id = target["landlord_id"]

        conn.execute("""
            INSERT INTO reports
            (reporter_id, reported_user_id, property_id,
             report_type, category, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            me["id"], reported_id, property_ref,
            report_type, category, details[:3000]
        ))

        conn.commit()
        conn.close()

        flash("Your report has been submitted privately to MOAGI.")
        return redirect(url_for("report"))

    return page("""
    <h1>Report a concern</h1>
    <p class="muted">
        Reports are private and reviewed by authorised MOAGI administrators.
        The person being reported will not be told who submitted the report.
    </p>

    <form method="post" class="card">
        <label>What are you reporting?</label>
        <select name="report_type" required>
            <option value="">Choose one</option>
            <option value="landlord">A landlord</option>
            <option value="tenant">A tenant</option>
            <option value="property">A property</option>
        </select>

        <label>Landlord or tenant account ID (if applicable)</label>
        <input name="reported_user_id" type="number" min="1"
               placeholder="Enter account ID">

        <label>Property ID (if reporting a property)</label>
        <input name="property_id" type="number" min="1"
               placeholder="Enter property ID">

        <label>Reason for report</label>
        <select name="category" required>
            <option value="">Choose a reason</option>
            <option value="Suspicious activity">Suspicious activity</option>
            <option value="Fraud or scam">Fraud or scam</option>
            <option value="Harassment">Harassment</option>
            <option value="False property listing">False property listing</option>
            <option value="Unsafe property">Unsafe property</option>
            <option value="Other">Other</option>
        </select>

        <label>Explain what happened</label>
        <textarea name="details" minlength="10" maxlength="3000"
                  required placeholder="Please describe your concern..."></textarea>

        <button class="btn">Submit private report</button>
    </form>
    """)



@app.route("/admin")
@login_required
def admin_dashboard():
    me = current_user()
    if me["role"] != "admin":
        abort(403)

    conn = db()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    property_count = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    open_reports = conn.execute("SELECT COUNT(*) FROM reports WHERE status='open'").fetchone()[0]
    report_count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    conn.close()

    return page("""
    <div class="eyebrow">MOAGI Administration</div>
    <h1>Welcome, {{me.first_name}}.</h1>
    <p class="muted">Manage the MOAGI platform.</p>
    <div class="grid">
        <div class="card"><div class="price">{{user_count}}</div><p>Registered users</p></div>
        <div class="card"><div class="price">{{property_count}}</div><p>Property listings</p></div>
        <div class="card"><div class="price">{{open_reports}}</div><p>Open reports</p></div>
        <div class="card"><div class="price">{{report_count}}</div><p>Total reports</p></div>
    </div>
    <div class="card">
        <h2>Reports and safety</h2>
        <p class="muted">Review reports submitted by MOAGI users.</p>
        <a class="btn" href="/admin/reports">Manage reports</a>
    </div>
    <p><a class="btn ghost" href="/">View website</a></p>
    """, me=me, user_count=user_count,
        property_count=property_count,
        open_reports=open_reports,
        report_count=report_count)

@app.route("/admin/reports/<int:report_id>/status", methods=["POST"])
@login_required
def update_report_status(report_id):
    me = current_user()

    if me["role"] != "admin":
        abort(403)

    status = request.form.get("status", "").strip()

    if status not in ("open", "under_review", "resolved"):
        abort(400)

    conn = db()

    report = conn.execute(
        "SELECT id FROM reports WHERE id=?",
        (report_id,)
    ).fetchone()

    if not report:
        conn.close()
        abort(404)

    conn.execute(
        "UPDATE reports SET status=? WHERE id=?",
        (status, report_id)
    )

    conn.commit()
    conn.close()

    flash("Report status updated successfully.")
    return redirect(url_for("admin_reports"))


@app.route("/admin/reports")
@login_required
def admin_reports():
    me = current_user()

    if me["role"] != "admin":
        abort(403)

    conn = db()
    reports = conn.execute("""
        SELECT r.*, reporter.first_name AS reporter_first,
               reporter.surname AS reporter_last,
               target.first_name AS target_first,
               target.surname AS target_last
        FROM reports r
        JOIN users reporter ON reporter.id = r.reporter_id
        LEFT JOIN users target ON target.id = r.reported_user_id
        ORDER BY r.created_at DESC, r.id DESC
    """).fetchall()
    conn.close()

    return page("""
    <h1>Private reports</h1>
    <p class="muted">Administrator access only.</p>

    {% for r in reports %}
    <article class="card">
        <h3>Report #{{r.id}} - {{r.category}}</h3>
        <p><b>Type:</b> {{r.report_type}}</p>
        <p><b>Reported account:</b>
            {{r.target_first or "Not specified"}}
            {{r.target_last or ""}}
        </p>
        <p><b>Property ID:</b> {{r.property_id or "N/A"}}</p>
        <p><b>Submitted by:</b>
            {{r.reporter_first}} {{r.reporter_last}}
        </p>
        <p><b>Details:</b> {{r.details}}</p>
        
<p><b>Status:</b> {{r.status}}</p>

<form method="POST" action="/admin/reports/{{r.id}}/status">
    <label>Update report status</label>
    <select name="status" required>
        <option value="open" {% if r.status == "open" %}selected{% endif %}>Open</option>
        <option value="under_review" {% if r.status == "under_review" %}selected{% endif %}>Under Review</option>
        <option value="resolved" {% if r.status == "resolved" %}selected{% endif %}>Resolved</option>
    </select>
    <button class="btn" type="submit">Save status</button>
</form>

        <p class="small">{{r.created_at}}</p>
    </article>
    {% else %}
    <p class="muted">No reports have been submitted.</p>
    {% endfor %}
    """, reports=reports)


@app.errorhandler(403)
def forbidden(_):
    return page("<h1>Not allowed</h1><p class='muted'>You don't have permission to view this page.</p>"), 403

@app.errorhandler(404)
def not_found(_):
    return page("<h1>Page not found</h1><p class='muted'>That page may have moved.</p><a class='btn' href='/'>Back home</a>"), 404

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print("MOAGI is running at http://0.0.0.0:%d" % port)
    print("Demo landlord: landlord@moagi.demo / DemoLandlord123!")
    print("Demo tenant: tenant@moagi.demo / DemoTenant123!")
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("MOAGI_DEBUG", "").lower() in ("1", "true", "yes"))


