# IELTS Speaking Practice Simulator

## Local development

### Backend (streaming API)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=your_key_here
uvicorn main:app --reload --port 8000
```

### Frontend (static UI)

```bash
python -m http.server 5173
```

Open `http://localhost:5173/index.html` in your browser and click the mic button to stream audio to the backend.
