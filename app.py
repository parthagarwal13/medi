import os
import secrets
import uuid
from datetime import datetime
from math import atan2, cos, radians, sin, sqrt

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash
from PIL import Image, UnidentifiedImageError
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder=None)
database_url = os.environ.get("DATABASE_URL", "sqlite:///medifind.db")
if os.environ.get("VERCEL") and not os.environ.get("DATABASE_URL"):
    raise RuntimeError("Set DATABASE_URL to the Neon pooled connection string in Vercel settings.")
if database_url.startswith("postgres://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
elif database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or ("local-dev-change-this-before-deployment" if not os.environ.get("VERCEL") else None)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("HTTPS_ONLY", "1" if os.environ.get("VERCEL") else "0") == "1"
if os.environ.get("VERCEL") and not app.config["SECRET_KEY"]:
    raise RuntimeError("Set SECRET_KEY in Vercel environment variables before deployment.")
if database_url.startswith("postgresql+"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 1, "max_overflow": 0}
db = SQLAlchemy(app)


class Pharmacy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), default="")
    address = db.Column(db.String(250), default="")
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    inventory = db.relationship("Inventory", backref="pharmacy", cascade="all, delete-orphan")
    account = db.relationship("Account", back_populates="pharmacy", uselist=False)


class Medicine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    salt = db.Column(db.String(250), nullable=False)
    category = db.Column(db.String(100), default="")
    uses = db.Column(db.String(500), default="")
    prescription_required = db.Column(db.Boolean, default=False)
    inventory = db.relationship("Inventory", backref="medicine", cascade="all, delete-orphan")


class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pharmacy_id = db.Column(db.Integer, db.ForeignKey("pharmacy.id"), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey("medicine.id"), nullable=False)
    stock = db.Column(db.Integer, default=0, nullable=False)
    price = db.Column(db.Float, default=0, nullable=False)
    image_url = db.Column(db.String(500))
    image_public_id = db.Column(db.String(250))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("pharmacy_id", "medicine_id", name="uq_inventory_shop_medicine"),)


class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    pharmacy_id = db.Column(db.Integer, db.ForeignKey("pharmacy.id"), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pharmacy = db.relationship("Pharmacy", back_populates="account")


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 6371.0 * 2 * atan2(sqrt(a), sqrt(1 - a))


def seed():
    if Medicine.query.count():
        return
    meds = [
        Medicine(name="Combiflam", salt="Ibuprofen 400 mg + Paracetamol 325 mg", category="Analgesic / Antipyretic", uses="Temporary relief of pain and fever. Follow the label or a qualified clinician's advice."),
        Medicine(name="Paracetamol 500", salt="Paracetamol 500 mg", category="Analgesic / Antipyretic", uses="Temporary relief of pain and fever when appropriate."),
        Medicine(name="Cetirizine 10", salt="Cetirizine Hydrochloride 10 mg", category="Antihistamine", uses="Relief of allergy symptoms such as sneezing and itching."),
        Medicine(name="Azithromycin 500", salt="Azithromycin 500 mg", category="Antibiotic", uses="For certain bacterial infections; use only under appropriate medical advice.", prescription_required=True),
        Medicine(name="Amoxicillin 500", salt="Amoxicillin 500 mg", category="Antibiotic", uses="For certain bacterial infections; use only under appropriate medical advice.", prescription_required=True),
        Medicine(name="ORS", salt="Oral Rehydration Salts", category="Rehydration", uses="Helps replace fluids and electrolytes during dehydration."),
    ]
    db.session.add_all(meds)
    db.session.flush()
    shops = [
        Pharmacy(name="City Care Pharmacy", owner="Rahul Sharma", phone="9876543210", address="Main Market", lat=23.456, lon=76.270, verified=True),
        Pharmacy(name="HealthPlus Medicals", owner="Neha Verma", phone="9876501234", address="Station Road", lat=23.461, lon=76.279, verified=True),
        Pharmacy(name="Shree Medical Store", owner="Amit Jain", phone="9876512345", address="College Road", lat=23.449, lon=76.286, verified=True),
        Pharmacy(name="New Life Pharmacy", owner="Demo Owner", phone="9876523456", address="Bus Stand", lat=23.470, lon=76.260, verified=False),
    ]
    db.session.add_all(shops)
    db.session.flush()
    rows = [(0,0,18,145),(0,1,30,28),(0,2,12,42),(0,3,0,118),(0,5,20,24),(1,0,6,139),(1,1,50,25),(1,2,18,40),(1,4,8,95),(1,5,12,23),(2,0,22,150),(2,1,0,27),(2,2,7,44),(2,3,10,120),(2,4,14,92),(3,0,10,148),(3,1,10,29)]
    for s, m, stock, price in rows:
        db.session.add(Inventory(pharmacy_id=shops[s].id, medicine_id=meds[m].id, stock=stock, price=price))
    db.session.commit()


def ensure_admin():
    email = os.environ.get("ADMIN_EMAIL", "admin@medifind.local").strip().lower()
    local_sqlite = database_url.startswith("sqlite:") and not os.environ.get("VERCEL")
    password = os.environ.get("ADMIN_PASSWORD") or ("Admin@12345" if local_sqlite else None)
    if not password:
        return
    if not Account.query.filter_by(role="admin").first():
        db.session.add(Account(name="MediFind Admin", email=email, password_hash=generate_password_hash(password), role="admin"))
        db.session.commit()


def initialize_database():
    db.create_all()
    inspector = inspect(db.engine)
    inventory_columns = {column["name"] for column in inspector.get_columns("inventory")}
    with db.engine.begin() as connection:
        if "image_url" not in inventory_columns:
            connection.execute(text("ALTER TABLE inventory ADD COLUMN image_url VARCHAR(500)"))
        if "image_public_id" not in inventory_columns:
            connection.execute(text("ALTER TABLE inventory ADD COLUMN image_public_id VARCHAR(250)"))
    if os.environ.get("DB_SEED_DEMO", "0" if database_url.startswith("postgresql+") else "1") == "1":
        seed()
    ensure_admin()


@app.cli.command("init-db")
def init_db_command():
    """Create/update schema and initialize local demo content."""
    initialize_database()
    print("Database schema initialized.")


def cloudinary_ready():
    return all(os.environ.get(key) for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"))


def upload_inventory_image(upload):
    if not upload or not upload.filename:
        return None
    if not cloudinary_ready():
        raise RuntimeError("Medicine photo upload is not configured yet. Add Cloudinary environment variables.")
    import cloudinary
    import cloudinary.uploader
    try:
        upload.stream.seek(0)
        image = Image.open(upload.stream)
        image.verify()
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError("Use a JPG, PNG, or WEBP image.")
        upload.stream.seek(0)
        cloudinary.config(cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"], api_key=os.environ["CLOUDINARY_API_KEY"], api_secret=os.environ["CLOUDINARY_API_SECRET"], secure=True)
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError("That file is not a valid image.") from exc
    try:
        result = cloudinary.uploader.upload(upload.stream, folder="medifind/medicines", public_id=uuid.uuid4().hex, resource_type="image", allowed_formats=["jpg", "jpeg", "png", "webp"], transformation=[{"width": 1200, "height": 1200, "crop": "limit"}])
        return result["secure_url"], result["public_id"]
    except Exception as exc:
        raise RuntimeError("Cloudinary could not save that photo. Check its configuration and try again.") from exc


def delete_cloudinary_image(public_id):
    if public_id and cloudinary_ready():
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"], api_key=os.environ["CLOUDINARY_API_KEY"], api_secret=os.environ["CLOUDINARY_API_SECRET"], secure=True)
        try:
            cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
        except Exception:
            pass


def current_account():
    account_id = session.get("account_id")
    return db.session.get(Account, account_id) if account_id else None


def require_role(*roles):
    account = current_account()
    if not account or not account.active:
        session.clear()
        flash("Please log in to continue.", "error")
        return None
    if account.role not in roles:
        abort(403)
    return account


@app.before_request
def csrf_guard():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(400, "Invalid or expired form token. Refresh and try again.")


@app.context_processor
def inject_globals():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["csrf_token"], "current_user": current_account()}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/style.css")
def stylesheet():
    return send_from_directory(os.path.join(app.root_path, "public"), "style.css")


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()[:120]
    try:
        lat = float(request.args.get("lat", "23.456"))
        lon = float(request.args.get("lon", "76.270"))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except ValueError:
        flash("Location coordinates were invalid. Showing results near the demo location.", "error")
        lat, lon = 23.456, 76.270
    medicines = Medicine.query.filter(db.or_(Medicine.name.ilike(f"%{q}%"), Medicine.salt.ilike(f"%{q}%"))).order_by(Medicine.name).all() if q else Medicine.query.order_by(Medicine.name).limit(20).all()
    results = []
    for med in medicines:
        rows = Inventory.query.join(Pharmacy).filter(Inventory.medicine_id == med.id, Pharmacy.verified.is_(True), Inventory.stock > 0).all()
        shops = [{"pharmacy": i.pharmacy.name, "pharmacy_id": i.pharmacy.id, "address": i.pharmacy.address, "phone": i.pharmacy.phone, "stock": i.stock, "price": i.price, "image_url": i.image_url, "distance": round(distance_km(lat, lon, i.pharmacy.lat, i.pharmacy.lon), 2), "lat": i.pharmacy.lat, "lon": i.pharmacy.lon} for i in rows]
        shops.sort(key=lambda x: (x["distance"], x["price"]))
        nearest_id = min(shops, key=lambda x: (x["distance"], x["price"]))["pharmacy_id"] if shops else None
        cheapest_id = min(shops, key=lambda x: (x["price"], x["distance"]))["pharmacy_id"] if shops else None
        ignored = {"mg", "g", "ml", "mcg", "microgram", "micrograms", "iu", "units", "tablet", "tablets"}
        tokens = {t.strip(".,()") for t in med.salt.lower().replace("+", " ").split() if any(c.isalpha() for c in t) and t.strip(".,()") not in ignored}
        alternatives = []
        if tokens:
            for other in Medicine.query.filter(Medicine.id != med.id).all():
                other_tokens = {t.strip(".,()") for t in other.salt.lower().replace("+", " ").split() if any(c.isalpha() for c in t) and t.strip(".,()") not in ignored}
                score = len(tokens & other_tokens)
                if score:
                    available = Inventory.query.join(Pharmacy).filter(Inventory.medicine_id == other.id, Pharmacy.verified.is_(True), Inventory.stock > 0).all()
                    if available:
                        nearest = min(available, key=lambda i: (distance_km(lat, lon, i.pharmacy.lat, i.pharmacy.lon), i.price))
                        alternatives.append({"name": other.name, "salt": other.salt, "score": score, "nearest": nearest.pharmacy.name, "distance": round(distance_km(lat, lon, nearest.pharmacy.lat, nearest.pharmacy.lon), 2), "price": nearest.price, "stock": nearest.stock, "phone": nearest.pharmacy.phone, "lat": nearest.pharmacy.lat, "lon": nearest.pharmacy.lon, "image_url": nearest.image_url})
        alternatives.sort(key=lambda x: (-x["score"], x["distance"], x["price"]))
        results.append({"medicine": med, "shops": shops, "nearest_id": nearest_id, "cheapest_id": cheapest_id, "alternatives": alternatives[:5]})
    return render_template("search.html", q=q, results=results, lat=lat, lon=lon)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        role = request.form.get("role", "customer")
        if role not in ("customer", "shopkeeper"):
            abort(400)
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or len(password) < 8 or "@" not in email:
            flash("Enter a name, valid email, and password with at least 8 characters.", "error")
            return render_template("register.html")
        if Account.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
            return render_template("register.html")
        shop = None
        if role == "shopkeeper":
            try:
                lat, lon = float(request.form["lat"]), float(request.form["lon"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError
            except (ValueError, KeyError):
                flash("Enter valid latitude and longitude.", "error")
                return render_template("register.html")
            shop = Pharmacy(name=request.form.get("shop_name", "").strip(), owner=name, phone=request.form.get("phone", "").strip(), address=request.form.get("address", "").strip(), lat=lat, lon=lon, verified=False)
            if not shop.name or not shop.address:
                flash("Pharmacy name and address are required.", "error")
                return render_template("register.html")
            db.session.add(shop)
            db.session.flush()
        account = Account(name=name, email=email, password_hash=generate_password_hash(password), role=role, pharmacy=shop)
        db.session.add(account)
        db.session.commit()
        session.clear()
        session["account_id"] = account.id
        flash("Account created. Your pharmacy will appear in search after admin verification.")
        return redirect(url_for("shop" if role == "shopkeeper" else "home"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        account = Account.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if not account or not check_password_hash(account.password_hash, request.form.get("password", "")):
            flash("Email or password is incorrect.", "error")
        elif not account.active:
            flash("This account is disabled. Contact the administrator.", "error")
        else:
            session.clear()
            session["account_id"] = account.id
            flash("Welcome back.")
            return redirect(url_for("admin" if account.role == "admin" else "shop" if account.role == "shopkeeper" else "home"))
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    flash("You are logged out.")
    return redirect(url_for("home"))


@app.route("/shop")
def shop():
    account = require_role("shopkeeper")
    if not account:
        return redirect(url_for("login"))
    if not account.pharmacy:
        abort(403)
    inventory = Inventory.query.filter_by(pharmacy_id=account.pharmacy.id).all()
    medicines = Medicine.query.order_by(Medicine.name).all()
    return render_template("shop.html", shop=account.pharmacy, inventory=inventory, medicines=medicines)


@app.post("/shop/inventory")
def update_inventory():
    account = require_role("shopkeeper")
    if not account:
        return redirect(url_for("login"))
    try:
        stock = int(request.form.get("stock", ""))
        price = float(request.form.get("price", ""))
        medicine_id = int(request.form.get("medicine_id", ""))
        if stock < 0 or price < 0 or price != price or price == float("inf"):
            raise ValueError
    except ValueError:
        flash("Enter a valid non-negative stock and price.", "error")
        return redirect(url_for("shop"))
    med = db.session.get(Medicine, medicine_id)
    if not med:
        abort(404)
    inv = Inventory.query.filter_by(pharmacy_id=account.pharmacy_id, medicine_id=medicine_id).first()
    uploaded_asset = None
    old_public_id = inv.image_public_id if inv else None
    try:
        uploaded_asset = upload_inventory_image(request.files.get("photo"))
    except (ValueError, RuntimeError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("shop"))
    if inv:
        inv.stock, inv.price = stock, price
    else:
        inv = Inventory(pharmacy_id=account.pharmacy_id, medicine_id=medicine_id, stock=stock, price=price)
        db.session.add(inv)
    if uploaded_asset:
        inv.image_url, inv.image_public_id = uploaded_asset
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        if uploaded_asset:
            delete_cloudinary_image(uploaded_asset[1])
        raise
    if uploaded_asset and old_public_id:
        delete_cloudinary_image(old_public_id)
    flash("Inventory updated.")
    return redirect(url_for("shop"))


@app.route("/admin")
def admin():
    account = require_role("admin")
    if not account:
        return redirect(url_for("login"))
    accounts = Account.query.order_by(Account.created_at.desc()).all()
    shops = Pharmacy.query.order_by(Pharmacy.created_at.desc()).all()
    return render_template("admin.html", accounts=accounts, shops=shops, medicines=Medicine.query.order_by(Medicine.name).all())


@app.post("/admin/user/<int:user_id>/toggle")
def toggle_user(user_id):
    account = require_role("admin")
    if not account:
        return redirect(url_for("login"))
    target = db.get_or_404(Account, user_id)
    if target.id == account.id:
        flash("You cannot disable your own admin account.", "error")
    else:
        target.active = not target.active
        db.session.commit()
        flash("Account status updated.")
    return redirect(url_for("admin"))


@app.post("/admin/verify/<int:shop_id>")
def verify(shop_id):
    if not require_role("admin"):
        return redirect(url_for("login"))
    shop = db.get_or_404(Pharmacy, shop_id)
    shop.verified = not shop.verified
    db.session.commit()
    flash("Pharmacy verification updated.")
    return redirect(url_for("admin"))


@app.post("/admin/add-shop")
def add_shop():
    if not require_role("admin"):
        return redirect(url_for("login"))
    try:
        lat, lon = float(request.form["lat"]), float(request.form["lon"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except (ValueError, KeyError):
        flash("Enter valid coordinates.", "error")
        return redirect(url_for("admin"))
    name, owner = request.form.get("name", "").strip(), request.form.get("owner", "").strip()
    if not name or not owner:
        flash("Pharmacy and owner names are required.", "error")
        return redirect(url_for("admin"))
    db.session.add(Pharmacy(name=name, owner=owner, phone=request.form.get("phone", "").strip(), address=request.form.get("address", "").strip(), lat=lat, lon=lon, verified=False))
    db.session.commit()
    flash("Shop added for verification.")
    return redirect(url_for("admin"))


@app.post("/admin/add-medicine")
def add_medicine():
    if not require_role("admin"):
        return redirect(url_for("login"))
    name = request.form.get("name", "").strip()
    salt = request.form.get("salt", "").strip()
    if not name or not salt:
        flash("Medicine name and active salt are required.", "error")
        return redirect(url_for("admin"))
    existing = Medicine.query.filter(db.func.lower(Medicine.name) == name.lower()).first()
    if existing:
        flash("A medicine with that name is already in the catalogue.", "error")
        return redirect(url_for("admin"))
    med = Medicine(name=name, salt=salt, category=request.form.get("category", "").strip(), uses=request.form.get("uses", "").strip(), prescription_required=request.form.get("prescription_required") == "on")
    db.session.add(med)
    db.session.commit()
    flash("Medicine added to the catalogue.")
    return redirect(url_for("admin"))


@app.route("/api/medicine/<int:medicine_id>")
def medicine_api(medicine_id):
    med = db.get_or_404(Medicine, medicine_id)
    return jsonify({"id": med.id, "name": med.name, "salt": med.salt, "category": med.category, "uses": med.uses, "prescription_required": med.prescription_required})


@app.route("/api/health")
def health_api():
    db.session.execute(text("SELECT 1"))
    return jsonify({"status": "ok", "database": "connected"})


if __name__ == "__main__":
    with app.app_context():
        initialize_database()
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
