# SecureRAG

A simple tool to chat with your PDFs. Upload documents, ask questions, and get answers.

### What it does:
- Upload up to 5 PDFs
- Ask questions about your documents
- Get summaries with specific focus
- Secure user accounts with login
- All data stored in MongoDB Atlas

---

## How to Use

### 1. Backend (Hugging Face Spaces)
- Create a new Space at [huggingface.co/new-space](https://huggingface.co/new-space)
- Choose Docker → Blank
- Upload files from `spaces/backend/`
- Add these secrets in Space settings:
  - `MONGODB_URI` — Your MongoDB connection string
  - `MONGODB_DB` — securerag
  - `GROQ_API_KEY` — Your Groq API key
  - `HF_TOKEN` — Your HuggingFace token
  - `JWT_SECRET` — Any random string
  - `LLM_BACKEND` — groq
- Update `main.py` line 19 with your Streamlit URL (for CORS)

### 2. Frontend (React JS + Vite)
- The frontend is a modern single-page application built with React and TailwindCSS.
- Deploy the `frontend/` directory to platforms like Vercel, Netlify, or GitHub Pages.
- **Environment Variable:** Add the following variable to your deployment platform so the frontend knows where the backend lives:
  - `VITE_API_BASE_URL` = `https://your-backend-url.com`

### 3. MongoDB Atlas
- Go to Network Access
- Add IP: Allow from Anywhere

---

## Run Locally

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload

# Frontend
cd frontend

# Install Node dependencies
npm install

# Create a local environment file
echo "VITE_API_BASE_URL=http://localhost:8000" > .env

# Start the Vite development server
npm run dev
```

---

## Tech Stack
Frontend:
- React 18 (Vite)
- TailwindCSS (Styling & UI)
- React Router (Navigation)
- GSAP (Smooth animations)
- Axios & React Hot Toast

Backend:
- FastAPI & Uvicorn (High-performance API)
- LangChain (Orchestration & Chains)
- PyMuPDF & LlamaParse (Document extraction & Image rendering)
- PyJWT & Passlib (Authentication)

AI & Data:
- MongoDB Atlas (Vector Search & Chat History storage)
- Groq (llama-3.3-70b-versatile & llama-4-scout Vision)
- HuggingFace (BAAI/bge-base-en-v1.5 for local embeddings)
- Cohere (Reranking)
