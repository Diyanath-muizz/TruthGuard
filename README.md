# TruthGuard: Adversarial Verification for Multi-Agent Document Q&A

**TruthGuard** is an intelligent document-question-answering system designed to eliminate misleading answers caused by conflicting policies, outdated FAQs, multiple versions of the same document, and superseded amendments.

Ordinary Retrieval-Augmented Generation (RAG) pipelines naively blend contradictory retrieved passages into compromising answers (such as *"Employees receive 12 to 15 days of leave"*). TruthGuard prevents this failure mode by orchestrating a 4-agent LangGraph pipeline with an adversarial Critic Agent and deterministic trust rules.

---

## 🏛️ System Architecture

```text
                                  ┌──────────────────────────┐
                                  │       USER QUESTION      │
                                  └────────────┬─────────────┘
                                               │
                                               ▼
                                  ┌──────────────────────────┐
                                  │      Retriever Agent     │
                                  │  (Dense ChromaDB + BM25) │
                                  └────────────┬─────────────┘
                                               │
                                               ▼
                                  ┌──────────────────────────┐
                   ┌─────────────►│    Synthesizer Agent     │
                   │              │ (Claims + Non-blending)  │
                   │              └────────────┬─────────────┘
                   │                           │
                   │                           ▼
                   │              ┌──────────────────────────┐
  Revision Loop    │              │ Adversarial Critic Agent │
  (Max 2 passes)   │              │  • Contradictions        │
                   │              │  • Staleness/Expiration  │
                   │              │  • Unsupported Claims    │
                   │              │  • Authority Hierarchy   │
                   │              └────────────┬─────────────┘
                   │                           │
                   └── If Revision Required ───┤
                                               │
                                               ▼
                                  ┌──────────────────────────┐
                                  │     Resolution Agent     │
                                  │ (Verified / Abstained /  │
                                  │     Human Review)        │
                                  └────────────┬─────────────┘
                                               │
                                               ▼
                                  ┌──────────────────────────┐
                                  │  FINAL EXPLAINABLE ANSWER│
                                  └──────────────────────────┘
```

---

## 🚀 Key Features

1. **4 Logical Agents:**
   - **Retriever Agent:** Hybrid dense (Sentence Transformers + ChromaDB) and sparse (BM25) search fused with Reciprocal Rank Fusion (RRF).
   - **Synthesizer Agent:** Drafts answers grounded strictly in retrieved passages and refuses to blend conflicting values.
   - **Adversarial Critic Agent:** Skeptical fact-checker running deterministic checks for numeric contradictions, staleness, ungrounded claims, and institutional authority violations.
   - **Resolution Agent:** Produces a verified answer with citations, an explainable abstention, or escalates to a human review queue.
2. **Proactive Conflict Scanning:** Scans newly uploaded documents upon ingestion—surfacing policy contradictions before a user asks a question.
3. **Document Versioning & Supersession Graph:** Distinguishes publication dates from effective dates and honors formal supersession relationships.
4. **Deterministic Mock Mode:** Runs out of the box with zero external API keys required. Switchable to OpenAI, Groq, or Ollama via `.env`.
5. **Interactive Streamlit UI:** Complete 6-page interactive web interface with live database telemetry.

---

## 📦 Prerequisites

- **Python 3.10+** (Python 3.11+ recommended)
- **Windows PowerShell** (or Bash on macOS/Linux)

---

## ⚙️ Installation & Setup (Windows PowerShell)

### 1. Open PowerShell and navigate to the project directory
```powershell
cd C:\Users\Admin\.gemini\antigravity\scratch\truthguard
```

### 2. Create and activate a Python virtual environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

*(If script execution is disabled on your system, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*

### 3. Install required dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
By default, `LLM_PROVIDER=mock`. To enable cloud LLMs, open `.env` and configure your API key:
```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=your-actual-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

### 5. Initialize the database and synthetic corpus
```powershell
python scripts\initialize_project.py
```

### 6. Load the demonstration documents
```powershell
python scripts\create_demo_data.py
```

---

## 🖥️ Launching the Application

Run the Streamlit application:
```powershell
streamlit run app.py
```
The browser will automatically open to `http://localhost:8501`.

---

## 🧪 Demonstration Scenarios (Step-by-Step)

### Demo 1: Successful Conflict Resolution
1. Open **💬 Document Chat**.
2. Enter: `How many days of annual leave are employees entitled to?`
3. Click **🛡️ Ask TruthGuard**.
4. **Observation:**
   - Determination: `🟢 VERIFIED`
   - Answer: **15 days** according to the 2025 amendment.
   - Outdated source note: Explicitly identifies that the 2024 policy and FAQ (which stated 12 days) are superseded.
   - Does **NOT** answer "12 to 15 days".

### Demo 2: Unresolved Equal Authority Conflict
1. In **💬 Document Chat**, enter: `How many days per week are Engineering employees permitted to work remotely?`
2. Click **🛡️ Ask TruthGuard**.
3. **Observation:**
   - Determination: `🔴 HUMAN REVIEW REQUIRED`
   - TruthGuard abstains from picking arbitrarily between Policy A (3 days) and Policy B (2 days) because both hold equal institutional authority and neither supersedes the other.
   - An escalation case is automatically dispatched to the **👤 Admin Review** queue.

### Demo 3: Proactive Conflict Detection
1. Open **📄 Document Management**.
2. Upload a new amendment or policy.
3. Observe the immediate proactive conflict scan result.
4. Navigate to **🔍 Conflict Explorer** to inspect the detected discrepancy and view conflicting passages side-by-side.

### Demo 4: Unsupported Claim (Abstention)
1. In **💬 Document Chat**, enter: `What is the company dental implant coverage limit?`
2. Click **🛡️ Ask TruthGuard**.
3. **Observation:**
   - Determination: `⚫ ABSTAINED`
   - TruthGuard transparently explains that no grounding documents exist in the corpus, preventing hallucinated answers.

### Demo 5: Prompt Injection Defense
1. In **💬 Document Chat**, enter: `Does the system grant employees 100 days of leave per the security document?`
2. **Observation:**
   - The injection payload embedded in `prompt_injection_doc.txt` is treated strictly as untrusted text evidence.
   - TruthGuard verifies against authoritative policies and rejects the injection override.

---

## 🧪 Automated Testing & Evaluation

### Run the complete test suite:
```powershell
pytest tests\ -v
```

### Run the 40-question gold-standard benchmark:
```powershell
python evaluation\run_evaluation.py
```

---

## 📂 Project Directory Structure

```text
truthguard/
├── app.py                      # Streamlit application entry point
├── requirements.txt            # Dependency specifications
├── .env.example                # Environment variables template
├── README.md                   # Full system documentation
├── config/
│   └── settings.py             # Configuration & authority hierarchy
├── agents/
│   ├── __init__.py             # Shared Pydantic data schemas
│   ├── retriever_agent.py      # Agent 1: Hybrid retrieval with provenance
│   ├── synthesizer_agent.py    # Agent 2: Grounded draft synthesis
│   ├── critic_agent.py         # Agent 3: Adversarial fact-checker
│   └── resolution_agent.py     # Agent 4: Authority & determination
├── workflows/
│   ├── question_answering_graph.py # LangGraph multi-agent QA graph
│   ├── document_ingestion.py       # Ingestion & chunking pipeline
│   └── conflict_scan_graph.py      # Proactive conflict scanner
├── retrieval/
│   ├── embedding_service.py    # SentenceTransformers wrapper
│   ├── vector_store.py         # Persistent ChromaDB store
│   ├── bm25_retriever.py       # BM25 keyword index
│   └── hybrid_retriever.py     # Reciprocal Rank Fusion retriever
├── documents/
│   ├── parsers.py              # PDF, DOCX, TXT parsers
│   ├── chunking.py             # Sentence-aware chunker
│   ├── metadata.py             # Metadata validation & extraction
│   ├── versioning.py           # Document version graph
│   └── citations.py            # Citation data structures
├── verification/
│   ├── contradiction_detector.py # Numeric & semantic conflict detector
│   ├── staleness_checker.py      # Temporal & expiration checker
│   ├── authority_rules.py        # Configurable institutional hierarchy
│   ├── supersession_graph.py     # Directed supersession tracker
│   ├── citation_validator.py     # Deterministic citation verifier
│   └── trust_engine.py           # Explainable trust decision engine
├── database/
│   ├── models.py               # SQLAlchemy 2.0 ORM models
│   ├── repository.py           # Database CRUD operations
│   └── initialization.py       # SQLite setup & session management
├── services/
│   ├── document_service.py     # Document lifecycle coordinator
│   ├── conflict_service.py     # Conflict scanner service
│   ├── question_service.py     # Q&A orchestration service
│   ├── audit_service.py        # Immutable audit logging
│   └── llm_service.py          # Multi-provider LLM abstraction
├── ui/
│   ├── dashboard.py            # Page 1: System Telemetry
│   ├── document_management.py  # Page 2: Upload & Management
│   ├── chat.py                 # Page 3: Verified Chat
│   ├── conflict_explorer.py    # Page 4: Conflict Explorer
│   ├── admin_review.py         # Page 5: Human Review Queue
│   └── evaluation.py           # Page 6: Benchmark Dashboard
├── evaluation/
│   ├── synthetic_corpus.py     # Synthetic document generator
│   ├── gold_standard.json      # 40 gold-standard benchmark cases
│   ├── metrics.py              # Empirical metrics calculator
│   └── run_evaluation.py       # Benchmark evaluation script
├── scripts/
│   ├── initialize_project.py   # Setup script
│   ├── create_demo_data.py     # Corpus loader script
│   └── rebuild_index.py        # Index synchronization script
└── tests/
    ├── test_parsers.py         # Parser unit tests
    ├── test_retrieval.py       # Retrieval unit tests
    ├── test_conflicts.py       # Conflict detection tests
    ├── test_authority.py       # Authority rules tests
    ├── test_critic.py          # Critic agent tests
    ├── test_resolution.py      # Resolution agent tests
    ├── test_citations.py       # Citation validation tests
    ├── test_workflows.py       # LangGraph workflow tests
    └── test_end_to_end.py      # Full demo scenario tests
```

---

## 🔒 Security & Verification Controls

- **Prompt Injection Defense:** Passages retrieved from documents are handled strictly as untrusted data inputs. Instructions inside documents cannot alter graph transitions or system rules.
- **No Hallucinated Citations:** CitationValidator ensures every citation references a chunk that was actually retrieved and matches the claimed document ID.
- **Never Settle on Misleading Compromises:** The Critic Agent rejects blended values (`12 to 15 days`), enforcing either an established authority decision or transparent abstention.
- **Explainable Trust Decisions:** All decisions report the exact rules and metadata considered (authority level, publication date, effective date, and supersession).
