# Context-Aware Multilingual Indian Legal Assistant

An AI-powered legal assistant designed to help users understand Indian law through multilingual conversations, document analysis, voice interaction, and source-grounded answers.

The application uses **Retrieval-Augmented Generation (RAG)** to retrieve relevant legal information and generate contextual responses using Google's Gemini API.

## Overview

Accessing and understanding legal information can be challenging because legal documents are lengthy, complex, and often difficult for ordinary users to interpret. Language barriers can make this even harder.

This project aims to make Indian legal information more accessible through a conversational interface that supports **English, Hindi, and Kannada**. Users can ask legal questions, upload documents, and interact using voice input while receiving answers grounded in retrieved legal sources.

## Key Features

- **Multilingual Legal Assistance:** Ask questions and receive responses in English, Hindi, or Kannada.
- **Context-Aware Conversations:** Uses conversation history to understand follow-up questions and maintain context.
- **Retrieval-Augmented Generation (RAG):** Retrieves relevant legal information before generating an answer.
- **Source-Grounded Responses:** Provides citations and source metadata from retrieved documents to help users verify answers.
- **Document Analysis:** Upload PDF, DOCX, or TXT files and ask questions about their contents.
- **Voice Input:** Ask questions using microphone input and speech transcription.
- **Legal Domain Classification:** Identifies the relevant legal domain and query type to improve retrieval.
- **Ambiguity Detection:** Identifies unclear questions and supports clarification.
- **Conversation Management:** Create, continue, rename, and delete conversations.
- **Retrieval Evaluation:** Includes evaluation scripts for metrics such as Precision@K, Recall@K, Mean Reciprocal Rank (MRR), and Hit Rate.

## Technology Stack

| Component | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Backend | Python, FastAPI |
| Language Model | Google Gemini API |
| Retrieval Architecture | Retrieval-Augmented Generation (RAG) |
| Embeddings | Sentence Transformers with multilingual embeddings |
| Vector Search | ChromaDB or FAISS, depending on configuration |
| Database | SQLite |
| Document Processing | PDF, DOCX, and text extraction utilities |
| Speech Processing | faster-whisper |
| Testing | Python test suite and evaluation scripts |
| Version Control | Git and GitHub |

## System Architecture

The application follows a retrieval-based question-answering workflow.

1. **User Input:** The user enters a question through text or voice, or uploads a document.
2. **Language and Query Understanding:** The system detects the language, classifies the legal domain, and identifies ambiguity.
3. **Context Processing:** Conversation history is used to interpret follow-up questions.
4. **Legal Information Retrieval:** Relevant document chunks are retrieved from the legal knowledge base.
5. **Ranking and Filtering:** Retrieved content is filtered by domain and ranked for relevance.
6. **Answer Generation:** Gemini generates a response using the retrieved context.
7. **Source Presentation:** The answer and available source information are returned to the user in the interface.

Uploaded documents can also be processed as a source of information for answering questions.

## Project Structure

```text
context-aware-multilingual-legal-assistant/
├── backend/
│   ├── app/
│   │   ├── api/              # API endpoints
│   │   ├── auth/             # Authentication and security
│   │   ├── database/         # Database models and repositories
│   │   ├── services/         # RAG, Gemini, retrieval, language and voice
│   │   └── main.py           # FastAPI application entry point
│   ├── tests/                # Backend tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # Reusable UI components
│   │   ├── context/          # Application context
│   │   ├── hooks/            # Custom React hooks
│   │   ├── pages/            # Application pages
│   │   └── services/         # Frontend API services
│   └── package.json
├── data_collection/          # Legal source manifests and source lists
├── scripts/                  # Data collection and processing pipeline
├── scripts2/                 # Additional pipeline scripts
├── evaluation/               # Retrieval evaluation tools and results
├── docker-compose.yml
├── ARCHITECTURE.md
├── RAG_PIPELINE.md
├── API_DOCUMENTATION.md
├── DATASET.md
└── README.md
```

## Getting Started

### Prerequisites

Install the following before running the application:

- Python 3.10 or a compatible version supported by the project dependencies
- Node.js and npm
- Git
- A Google Gemini API key
- Internet access to install dependencies and download required models

### 1. Clone the Repository

```bash
git clone https://github.com/Vidyashreev623/Context-aware-multilingual-legal-assistant.git
cd Context-aware-multilingual-legal-assistant
```

### 2. Set Up the Backend

Create and activate a virtual environment from the project root.

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

**macOS/Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Create `backend/.env` and configure the environment variables required by the application, including your Gemini API key and any database, embedding, or vector-store settings used by your configuration.

```env
GEMINI_API_KEY=your_gemini_api_key
```

Keep your actual API key private. Never commit `.env` files to GitHub.

Start the backend:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Backend endpoints:

- API documentation: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

### 3. Set Up the Frontend

Open another terminal from the project root:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually:

http://localhost:5173

Configure the frontend API base URL according to the project's frontend environment configuration.

### 4. Prepare the Legal Knowledge Base

The RAG pipeline requires legal documents to be collected and processed before meaningful retrieval from the legal knowledge base can be demonstrated.

The general workflow is:

1. Collect legal documents from appropriate sources.
2. Extract and normalize document text.
3. Split documents into meaningful chunks and attach metadata.
4. Generate multilingual embeddings.
5. Build the vector index.
6. Evaluate retrieval quality.

Refer to `DATASET.md` and `RAG_PIPELINE.md` for the project's data-processing workflow and configuration.

## Testing and Evaluation

The project includes backend tests and a retrieval evaluation harness.

Run the dependency-free test subset:

```bash
python backend/tests/run_tests.py
```

Run the pytest suite after installing the required dependencies:

```bash
pytest backend/tests/ -v
```

Evaluate retrieval:

```bash
python evaluation/evaluate.py
```

**Evaluation note:** Retrieval results produced using synthetic fixtures should not be interpreted as real-world legal retrieval performance. Evaluation against a populated legal corpus is required to assess practical effectiveness.

## Current Project Status

The application code, frontend, backend services, data-processing scripts, tests, and documentation are included in the repository.

Before demonstrating the complete system with real legal queries, ensure that the required dependencies and providers are configured, real legal documents have been collected and processed, the vector index has been built, and the live application has been tested end to end.

## Future Improvements

- Expand and validate the legal knowledge base using authoritative Indian legal sources.
- Improve retrieval accuracy and multilingual evaluation using real legal queries.
- Enhance answer quality through additional retrieval and ranking experiments.
- Improve deployment, monitoring, and production security.
- Expand automated and manual testing across languages, legal domains, and document types.

## Disclaimer

This project is intended for legal information and educational purposes. AI-generated responses may be incomplete or inaccurate and should not be treated as a substitute for advice from a qualified legal professional. Users should verify important information against authoritative legal sources.

## Author

**Vidyashree V**

GitHub: [Vidyashreev623](https://github.com/Vidyashreev623)

Project Repository: [Context-Aware Multilingual Indian Legal Assistant](https://github.com/Vidyashreev623/Context-aware-multilingual-legal-assistant)
