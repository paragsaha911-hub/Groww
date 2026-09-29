# Groww Mutual Fund RAG Assistant

An end-to-end, lightweight Retrieval-Augmented Generation (RAG) assistant designed to answer factual, compliance-aligned queries across key mutual fund schemes (such as HDFC Large Cap Fund, HDFC ELSS Tax Saver Fund, and HDFC Balanced Advantage Fund)[cite: 16]. 

The application utilizes hybrid retrieval (BM25 keyword search + dense vector search via ChromaDB), low-memory ONNX embeddings via FastEmbed, and LLM synthesis powered by Groq. The UI is built using Streamlit[cite: 2].

---

## Key Features

- Hybrid Retrieval: Combines BM25 lexical keyword matching with dense semantic embeddings for balanced factual precision and conceptual matching.
- Optimized for Low-RAM Environments: Designed to stay comfortably under the 512 MB memory threshold on constrained cloud instances (such as Render Free Tier)[cite: 1] by leveraging quantized ONNX models via fastembed instead of heavy PyTorch dependencies.
- Guardrails & Hallucination Defense:
  - PII scrubbing before LLM synthesis.
  - Strict scope enforcement and out-of-domain rejection.
  - Similarity floor checks to reject ungrounded or speculative answers[cite: 16].
  - Citations linking directly back to official SID/KIM source sections[cite: 2].

---

## Architecture Overview

User Query
    │
    ├──► PII & Intent Guardrails
    │
    ├──► Query Embedding (FastEmbed: sentence-transformers/all-MiniLM-L6-v2)
    │
    ├──► Hybrid Retrieval
    │     ├── BM25 Keyword Search
    │     └── ChromaDB Vector Search (hnsw:space cosine)
    │
    ├──► Similarity Floor & Heuristic Filtering
    │
    └──► Context Synthesis (Groq LLM) ──► Grounded Response + Source Citation

---

## Local Setup & Installation

1. Clone the Repository:
   git clone https://github.com/paragsaha911-hub/Groww.git
   cd Groww

2. Set Up Virtual Environment:
   python -m venv venv
   # On Windows (Git Bash):
   source venv/Scripts/activate
   # On Linux / macOS:
   source venv/bin/activate

3. Install Dependencies:
   pip install -r requirements.txt

4. Configure Environment Variables:
   Create a .env file in the root directory (referencing .env.example)[cite: 2]:
   GROQ_API_KEY=your_groq_api_key_here
   DISABLE_CROSS_ENCODER=true

5. Build/Rebuild Vector Index:
   To process raw scheme documents and generate local ChromaDB vectors[cite: 2]:
   python -m scripts.ingest --rebuild

6. Run the Application:
   streamlit run app/ui.py

---

## Deployment on Render

This repository is optimized for deployment as a Render Web Service[cite: 1]:

- Build Command:
  pip install -r requirements.txt && python -m scripts.ingest --rebuild

- Start Command:
  streamlit run app/ui.py --server.port $PORT --server.address 0.0.0.0 --server.fileWatcherType none --server.headless true

- Environment Variables:
  GROQ_API_KEY: <your-groq-key>
  DISABLE_CROSS_ENCODER: true

---

## Sample Questions & Answers

1. Scheme Fact / Expense Ratio
Question: What is the expense ratio of HDFC Large Cap Fund?[cite: 16]
Answer: According to the latest scheme disclosures, the Direct Plan of the HDFC Large Cap Fund has an expense ratio of approximately 0.90%, whereas the Regular Plan has an expense ratio of approximately 1.65% (inclusive of GST and management fees).
Source: HDFC Large Cap Fund - Scheme Information Document (SID) > Fund Facts

2. Statutory Lock-in & Exit Load
Question: Is there an exit load on HDFC ELSS Tax Saver Fund?[cite: 16]
Answer: No, there is Nil (0%) exit load on HDFC ELSS Tax Saver Fund. However, investments are subject to a mandatory statutory lock-in period of 3 years from the date of allotment under Section 80C rules. Units cannot be redeemed or switched out before the 3-year period expires.
Source: HDFC ELSS Tax Saver Fund > Key Information Memorandum (KIM) > Fees and Loads

3. Risk Profile & Asset Allocation
Question: What is the riskometer level of HDFC Balanced Advantage Fund?[cite: 16]
Answer: The riskometer level for HDFC Balanced Advantage Fund is categorized as "Very High Risk" due to its dynamic asset allocation model investing in a mix of equity instruments, derivatives, and fixed-income debt securities.
Source: HDFC Balanced Advantage Fund > Riskometer Disclosure

4. Minimum Investment / SIP Terms
Question: What is the minimum SIP amount for investing in this fund?
Answer: The minimum Systematic Investment Plan (SIP) installment for the scheme is ₹100 per month (and in multiples of ₹1 thereafter) for a minimum of 6 installments.
Source: Scheme Information Document > Investment Details

5. Out-of-Scope / Non-Answerable Handling
Question: Who will win the next ICC Cricket World Cup?
Answer: I could not find that in my sources. This assistant is specialized only for answering factual questions regarding mutual fund scheme documents, expense ratios, riskometers, and exit loads.

---

## Running Tests

Run the test suite locally to verify parsing, indexing, and retriever components[cite: 2]:
pytest
