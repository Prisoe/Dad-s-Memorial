from fastapi import FastAPI, Request, Depends, HTTPException, UploadFile, File, Form
import zipfile, tempfile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from PIL import Image, ExifTags
import os, shutil, uuid, html, re

from database import get_db, create_tables, Tribute, Photo, RateLimit

# ── App setup ──────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
# Use /data (Render persistent disk) if available, else local
DATA_DIR    = "/data" if os.path.exists("/data") else BASE_DIR
UPLOAD_DIR  = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Pastor Mike Alabi Memorial")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
# Serve uploaded photos from persistent disk
from starlette.staticfiles import StaticFiles as SF
app.mount("/uploads", SF(directory=UPLOAD_DIR), name="uploads")

@app.on_event("startup")
def startup():
    create_tables()
    _seed_photos_if_empty()


# ── Helpers ────────────────────────────────────────────────
MAX_TRIBUTE_LEN = 600
RATE_LIMIT_SECS = 60
ALLOWED_EXT     = {".jpg", ".jpeg", ".png", ".webp"}

def sanitize(text: str, max_len: int = 200) -> str:
    text = html.escape(text.strip())
    text = re.sub(r'[<>{}|\\^`]', '', text)
    return text[:max_len]

def check_rate_limit(ip: str, action: str, db: Session) -> bool:
    cutoff = datetime.utcnow() - timedelta(seconds=RATE_LIMIT_SECS)
    recent = db.query(RateLimit).filter(
        RateLimit.ip_address == ip,
        RateLimit.action == action,
        RateLimit.created_at > cutoff
    ).first()
    return recent is None

def record_rate_limit(ip: str, action: str, db: Session):
    db.add(RateLimit(ip_address=ip, action=action))
    db.commit()
    # Clean old records
    cutoff = datetime.utcnow() - timedelta(hours=2)
    db.query(RateLimit).filter(RateLimit.created_at < cutoff).delete()
    db.commit()

def fix_image_orientation(img: Image.Image) -> Image.Image:
    """Auto-rotate based on EXIF data."""
    try:
        exif = img._getexif()
        if exif:
            for tag, val in exif.items():
                if ExifTags.TAGS.get(tag) == 'Orientation':
                    if val == 3:   img = img.rotate(180, expand=True)
                    elif val == 6: img = img.rotate(270, expand=True)
                    elif val == 8: img = img.rotate(90,  expand=True)
                    break
    except Exception:
        pass
    return img

def process_photo(src_path: str, dest_path: str, target_w=600, target_h=800):
    """Fix orientation, crop to portrait 3:4, save optimised."""
    img = Image.open(src_path).convert("RGB")
    img = fix_image_orientation(img)

    # If landscape, rotate 90° to make portrait
    if img.width > img.height:
        img = img.rotate(90, expand=True)

    # Centre-crop to 3:4 portrait
    w, h = img.size
    target_ratio = 3 / 4
    current_ratio = w / h

    if current_ratio > target_ratio:          # too wide
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    elif current_ratio < target_ratio:        # too tall
        new_h = int(w / target_ratio)
        top = max(0, (h - new_h) // 4)       # bias toward top (faces)
        img = img.crop((0, top, w, top + new_h))

    img = img.resize((target_w, target_h), Image.LANCZOS)
    img.save(dest_path, "JPEG", quality=82, optimize=True)

def _seed_photos_if_empty():
    """Seed DB from whatever .jpg files already exist in static/uploads/."""
    db = next(get_db())
    if db.query(Photo).count() > 0:
        db.close()
        return

    captions = [
        "A portrait of Pastor Mike", "The Alabi family portrait",
        "Regal in gold", "Quiet strength", "At the RCCG pulpit",
        "With his beloved", "The church family", "Family and faith",
        "A cherished memory", "Portrait of a pastor",
        "A man of dignity", "Joy that lights every room",
        "Ministering with open hands", "With family after service",
        "A loving partnership", "Dressed in grace",
        "Sharp and dapper", "Christmas celebration",
        "Always smiling", "A man at peace",
    ]

    files = sorted([
        f for f in os.listdir(UPLOAD_DIR)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
    ])

    if not files:
        db.close()
        print("⚠ No photos found in uploads folder to seed.")
        return

    for i, fname in enumerate(files):
        caption = captions[i] if i < len(captions) else f"Photo {i+1}"
        db.add(Photo(filename=fname, caption=caption, sort_order=i, active=True, bg_rotation=(i < 20)))

    db.commit()
    db.close()
    print(f"✓ Photos seeded: {len(files)} photos from uploads folder")


# ── Routes ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(BASE_DIR, "index.html")) as f:
        return HTMLResponse(f.read())


# ── Tributes API ───────────────────────────────────────────

@app.get("/api/tributes")
def get_tributes(db: Session = Depends(get_db)):
    tributes = db.query(Tribute).filter(Tribute.approved == True)\
                 .order_by(Tribute.created_at.desc()).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "location": t.location,
            "relation": t.relation,
            "message": t.message,
            "date": t.created_at.strftime("%d %B %Y")
        }
        for t in tributes
    ]

@app.post("/api/tributes")
async def post_tribute(
    request: Request,
    name:     str = Form(...),
    location: str = Form(""),
    relation: str = Form(""),
    message:  str = Form(...),
    db: Session = Depends(get_db)
):
    ip = request.client.host

    if not check_rate_limit(ip, "tribute", db):
        raise HTTPException(429, "Please wait a moment before submitting again.")

    name    = sanitize(name, 100)
    location = sanitize(location, 100)
    relation = sanitize(relation, 100)
    message  = sanitize(message, MAX_TRIBUTE_LEN)

    if not name or not message:
        raise HTTPException(400, "Name and message are required.")
    if len(message) > MAX_TRIBUTE_LEN:
        raise HTTPException(400, "Message too long.")

    tribute = Tribute(name=name, location=location, relation=relation, message=message)
    db.add(tribute)
    db.commit()
    record_rate_limit(ip, "tribute", db)

    return {"success": True, "id": tribute.id}

@app.delete("/api/tributes/{tribute_id}")
def delete_tribute(tribute_id: int, db: Session = Depends(get_db)):
    t = db.query(Tribute).filter(Tribute.id == tribute_id).first()
    if not t:
        raise HTTPException(404, "Tribute not found.")
    db.delete(t)
    db.commit()
    return {"success": True}


# ── Photos API ─────────────────────────────────────────────

@app.get("/api/photos/bg")
def get_bg_photos(db: Session = Depends(get_db)):
    """Return only photos marked for background rotation."""
    photos = db.query(Photo).filter(Photo.active == True, Photo.bg_rotation == True)\
               .order_by(Photo.sort_order).all()
    # Fallback: if none marked, return first 20 active photos
    if not photos:
        photos = db.query(Photo).filter(Photo.active == True)\
                   .order_by(Photo.sort_order).limit(20).all()
    return [
        {"id": p.id, "url": f"/uploads/{p.filename}", "caption": p.caption}
        for p in photos
    ]

@app.patch("/api/photos/{photo_id}/bg")
def toggle_bg_rotation(photo_id: int, enabled: bool, db: Session = Depends(get_db)):
    """Toggle whether a photo appears in the background rotation."""
    p = db.query(Photo).filter(Photo.id == photo_id).first()
    if not p:
        raise HTTPException(404, "Photo not found.")
    # Max 20 in rotation
    if enabled:
        current_count = db.query(Photo).filter(Photo.bg_rotation == True).count()
        if current_count >= 20:
            raise HTTPException(400, "Maximum 20 photos in background rotation. Remove one first.")
    p.bg_rotation = enabled
    db.commit()
    return {"success": True, "id": photo_id, "bg_rotation": enabled}


@app.get("/api/photos")
def get_photos(db: Session = Depends(get_db)):
    photos = db.query(Photo).filter(Photo.active == True)\
               .order_by(Photo.sort_order).all()
    return [
        {"id": p.id, "url": f"/uploads/{p.filename}", "caption": p.caption, "bg_rotation": p.bg_rotation}
        for p in photos
    ]

@app.post("/api/photos/bulk")
async def bulk_upload_photos(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a zip file containing multiple photos — processes all at once."""
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(400, "Please upload a .zip file.")

    # Save zip to temp location
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "upload.zip")
        with open(zip_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Check it's a valid zip
        if not zipfile.is_zipfile(zip_path):
            raise HTTPException(400, "Invalid zip file.")

        processed, skipped, errors = [], [], []
        max_order = db.query(Photo).count()

        with zipfile.ZipFile(zip_path, 'r') as zf:
            members = [
                m for m in zf.namelist()
                if not m.startswith('__MACOSX')
                and not os.path.basename(m).startswith('.')
                and os.path.splitext(m)[1].lower() in {'.jpg','.jpeg','.png','.webp'}
            ]

            for member in members:
                try:
                    # Extract to temp
                    tmp_src = os.path.join(tmpdir, os.path.basename(member))
                    with zf.open(member) as src, open(tmp_src, 'wb') as dst:
                        dst.write(src.read())

                    # Process to portrait
                    dest_name = f"photo_{uuid.uuid4().hex[:12]}.jpg"
                    dest_path = os.path.join(UPLOAD_DIR, dest_name)
                    process_photo(tmp_src, dest_path)

                    # Save to DB
                    caption = os.path.splitext(os.path.basename(member))[0].replace('_',' ').replace('-',' ')
                    db.add(Photo(
                        filename=dest_name,
                        caption=caption[:200],
                        sort_order=max_order,
                        active=True,
                        bg_rotation=False
                    ))
                    max_order += 1
                    processed.append(os.path.basename(member))

                except Exception as e:
                    errors.append(f"{os.path.basename(member)}: {str(e)}")

        db.commit()

    return {
        "success": True,
        "processed": len(processed),
        "skipped": len(skipped),
        "errors": errors,
        "message": f"✓ {len(processed)} photos uploaded successfully."
    }


@app.post("/api/photos")
async def upload_photo(
    request: Request,
    file:    UploadFile = File(...),
    caption: str        = Form(""),
    db: Session = Depends(get_db)
):
    ip = request.client.host
    if not check_rate_limit(ip, "photo_upload", db):
        raise HTTPException(429, "Upload rate limit exceeded.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Only JPG, PNG, WEBP files allowed.")

    if file.size and file.size > 15 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 15MB).")

    tmp_name = f"tmp_{uuid.uuid4().hex}{ext}"
    tmp_path = os.path.join(UPLOAD_DIR, tmp_name)

    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    dest_name = f"photo_{uuid.uuid4().hex[:12]}.jpg"
    dest_path = os.path.join(UPLOAD_DIR, dest_name)

    try:
        process_photo(tmp_path, dest_path)
    except Exception as e:
        os.remove(tmp_path)
        raise HTTPException(500, f"Image processing failed: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    max_order = db.query(Photo).count()
    caption   = sanitize(caption, 200)
    photo     = Photo(filename=dest_name, caption=caption, sort_order=max_order)
    db.add(photo)
    db.commit()
    record_rate_limit(ip, "photo_upload", db)

    return {"success": True, "id": photo.id, "url": f"/static/uploads/{dest_name}"}

@app.delete("/api/photos/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    p = db.query(Photo).filter(Photo.id == photo_id).first()
    if not p:
        raise HTTPException(404, "Photo not found.")
    # Remove file
    fpath = os.path.join(UPLOAD_DIR, p.filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    db.delete(p)
    db.commit()
    return {"success": True}
