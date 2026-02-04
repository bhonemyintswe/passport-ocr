# Passport OCR - Hotel Guest Registration System

A web application for hotel front desk staff to extract guest passport data using OCR and export to Excel.

## Features

- Simple password-protected login
- Drag-and-drop passport image upload
- Auto-detection of multiple passports per image (1-3 passports per scan)
- MRZ (Machine Readable Zone) parsing for accurate data extraction
- Editable data table with inline editing
- One-click Excel export

## Tech Stack

- **Frontend**: React + Vite + Tailwind CSS
- **Backend**: Python FastAPI
- **OCR**: Tesseract + passporteye/mrz libraries (free, no API keys)
- **Hosting**: Vercel (frontend) + Render.com (backend)

## Local Development Setup

### Prerequisites

- Node.js 18+
- Python 3.11+
- Tesseract OCR installed on your system

#### Install Tesseract OCR

**Windows:**
```bash
# Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
# Or use chocolatey:
choco install tesseract
```

**macOS:**
```bash
brew install tesseract
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install tesseract-ocr
```

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp ../.env.example .env
# Edit .env to set your APP_PASSWORD and SECRET_KEY

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create .env file (optional for local dev - uses proxy)
cp .env.example .env

# Run the development server
npm run dev
```

The frontend will be available at `http://localhost:5173`

### Default Login Credentials

- **Username**: `admin`
- **Password**: `hotel2024` (or your custom APP_PASSWORD)

## Deployment

### Backend on Render.com

1. Create a new Web Service on Render.com
2. Connect your GitHub repository
3. Configure:
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables:
   - `APP_PASSWORD`: Your secure password
   - `SECRET_KEY`: A random secret string
   - `CORS_ORIGINS`: Your Vercel frontend URL

**Note**: For Tesseract support on Render, use the Dockerfile:
- Set build to "Docker" instead of "Python"
- The Dockerfile will install Tesseract automatically

### Frontend on Vercel

1. Create a new project on Vercel
2. Connect your GitHub repository
3. Configure:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Vite
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Add environment variable:
   - `VITE_API_URL`: Your Render backend URL (e.g., `https://passport-ocr-api.onrender.com`)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health` | GET | Health check for deployment |
| `/api/login` | POST | Authenticate user |
| `/api/ocr` | POST | Process passport images |
| `/api/export` | POST | Export data to Excel |

## Project Structure

```
passport-ocr/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── LoginPage.jsx
│   │   │   ├── UploadPage.jsx
│   │   │   └── DataTable.jsx
│   │   ├── api.js
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── vercel.json
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── auth.py
│   │   └── ocr_service.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── render.yaml
├── .env.example
└── README.md
```

## Privacy & Security

- No data persistence - all data is cleared on page refresh
- JWT-based session authentication
- Images are processed in memory and not stored
- Passwords should be set via environment variables

## Tips for Best OCR Results

1. Ensure the MRZ (machine readable zone at bottom) is clearly visible
2. Use high resolution scans (300 DPI recommended)
3. You can scan multiple passports on one page (up to 3)
4. Avoid glare, shadows, and blurry images
5. Ensure passport is not tilted more than 10 degrees

## License

MIT
