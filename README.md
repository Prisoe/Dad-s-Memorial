# Pastor Mike Adesoji Alabi — Memorial Website

## Project Structure
```
memorial-site/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, all routes
│   └── database.py      # SQLAlchemy models
├── static/
│   └── uploads/         # Processed photos stored here
├── templates/
│   └── index.html       # Full frontend (SPA)
├── requirements.txt
└── memorial.db          # SQLite DB (auto-created on first run)
```

## Setup & Run

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the server
uvicorn app.main:app --reload --port 8000

# 4. Open browser
# http://localhost:8000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/photos` | List all active photos |
| POST | `/api/photos` | Upload a new photo (multipart) |
| DELETE | `/api/photos/{id}` | Delete a photo |
| GET | `/api/tributes` | List all approved tributes |
| POST | `/api/tributes` | Submit a tribute (multipart) |
| DELETE | `/api/tributes/{id}` | Delete a tribute |

## Photo Upload (curl example)
```bash
curl -X POST http://localhost:8000/api/photos \
  -F "file=@photo.jpg" \
  -F "caption=A beautiful memory"
```

## Features
- All photos auto-corrected for EXIF rotation
- All photos cropped to portrait 3:4 format automatically
- Right-click / download blocked on all images
- Rate limiting: 1 tribute per minute per IP, upload throttled
- Input sanitization on all form fields
- Photos and tributes persist in SQLite database
- Background slideshow pulls from DB (updates live)

## Deployment (Render.com — Free)
1. Push to GitHub
2. Create new Web Service on render.com
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Done — live URL in minutes

## Admin: Deleting a tribute or photo
```bash
# Delete tribute with ID 5
curl -X DELETE http://localhost:8000/api/tributes/5

# Delete photo with ID 3
curl -X DELETE http://localhost:8000/api/photos/3
```
Or use any REST client (Postman, Insomnia, etc.)
