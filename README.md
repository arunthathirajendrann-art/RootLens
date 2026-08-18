# RootLens Incident Response AI

A 5-screen Copilot UI for automated incident response, combining a React frontend with a FastAPI backend, powered by the Google Gemini API.

## Requirements
- Python 3.10+
- Node.js 18+
- A valid Gemini API Key

## Setup & Installation

### 1. Backend Setup (FastAPI)
Navigate to the root directory and install Python dependencies:
```bash
pip install -r requirements.txt
```

Create a `.env` file in the root directory and add your Gemini API Key:
```env
GEMINI_API_KEY=your_actual_api_key_here
```

Start the FastAPI backend server:
```bash
python -m uvicorn api:app --reload --port 8000
```

### 2. Frontend Setup (React + Vite)
In a new terminal window, navigate to the `frontend` folder and install NPM dependencies:
```bash
cd frontend
npm install
```

Start the Vite development server:
```bash
npm run dev
```

### 3. Usage
Open your browser to the local URL provided by Vite (usually `http://localhost:5173`).
Upload your incident payload (alerts, metrics, logs, deploys) from the `data/` folder and the `sample_repo.zip` to run the AI incident analysis pipeline!
