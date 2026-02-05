# Local LLM + RAG + Qdrant on a Mac (mini M4)

This is a textbook local RAG pipeline. Ollama runs the pre???trained Mistral model, Qdrant holds vectors for the PDFs, and the app glues them together so Mistral can answer questions grounded in those open-education documents.

How this setup maps to "proper" RAG:
- You ingest PDFs, chunk them, embed each chunk, and store those embeddings + text in Qdrant???this is the retrieval index.
- On a question, you embed the query, ask Qdrant for nearest chunks, then send ???context chunks + user question??? to Mistral via Ollama.
- Mistral itself stays frozen; it just "reads" the retrieved PDF snippets in the prompt and synthesizes an answer, which is exactly how RAG is described in Qdrant/Ollama examples.
???
You are giving your local engine a searchable memory (Qdrant) of those PDFs and letting it reason over that supplemental data at query time.

---

```mermaid
graph TD
    %% Core metaphor
    User[User<br/>&lpar;Driver&rpar;]
    Ollama[Ollama<br/>&lpar;Car&rpar;]
    Mistral[Mistral AI<br/>&lpar;Engine&rpar;]
    RAG[RAG Pipeline<br/>&lpar;Fuel Injection / GPS&rpar;]

    %% Storage & fuel metaphor
    Embeds[Embedding Model<br/>&lpar;Refinery&rpar;]
    Qdrant[Qdrant Vector DB<br/>&lpar;Gas Tank + Fuel Lines&rpar;]

    %% Knowledge sources
    OER[Open Educational<br/>Resources &lpar;OER&rpar;]
    Docs[Documents & Notes]
    Ingest[Ingestion<br/>Process]

    %% Questions
    Questions[User Questions]

    %% Main flow
    User -->|Asks question| Questions
    Questions -->|Send to| Ollama
    Ollama -->|Uses| Mistral
    Ollama -->|Uses| RAG

    %% RAG internals &lpar;fuel system&rpar;
    RAG -->|Converts text to vectors| Embeds
    Embeds -->|Stores refined fuel| Qdrant
    Qdrant -->|Provides relevant fuel<br/>&lpar;chunks&rpar;| RAG

    %% Data side &lpar;fuel creation&rpar;
    OER --> Docs
    Docs --> Ingest
    Ingest -->|Clean & chunk| Docs
    Ingest -->|Embed & store| Embeds
    Ingest --> Qdrant

    %% Answer back
    RAG -->|Context + question| Mistral
    Mistral -->|Generates answer| Ollama
    Ollama -->|Returns answer| User
```

---

## 1. Prerequisites

1. Hardware  
   - Mac with 32 GB RAM.

2. Software  
   - Homebrew installed.  
   - Docker Desktop for Mac installed and running (for Qdrant).  
   - Python 3 (system or from python.org).

---

## 2. Enable SSH (optional, for headless use)

In **Terminal**:

```bash
sudo systemsetup -setremotelogin on
sudo systemsetup -getremotelogin
# Should print: Remote Login: On
```

(If it complains about Full Disk Access, enable **Remote Login** once in System Settings ??? General ??? Sharing.)

---

## 3. Install Homebrew and Docker

If Homebrew is not installed:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Install Docker Desktop (download from docker.com), then:

- Start Docker Desktop.  
- Verify:

```bash
docker ps
```

---

## 4. Install Ollama and models

Install Ollama:

```bash
brew install ollama
```

Start the Ollama server:

```bash
ollama serve
```

Pull models:

```bash
ollama pull mistral
ollama pull nomic-embed-text
```

---

## 5. Start Qdrant (vector database)

With Docker running:

```bash
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -v qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

Check:

```bash
docker ps
# qdrant container should be listed
```

---

## 6. Create project structure

```bash
mkdir -p ~/projects/llm-rag/{src,pdf}
cd ~/projects/llm-rag
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install qdrant-client httpx python-dotenv beautifulsoup4 lxml pypdf
```

Create `.env`:

```bash
cat > .env << 'EOF'
OLLAMA_BASE_URL=http://127.0.0.1:11434
EMBED_MODEL=nomic-embed-text
CHAT_MODEL=mistral
QDRANT_HOST=127.0.0.1
QDRANT_PORT=6333
QDRANT_COLLECTION=docs
EOF
```

---

## 7. Core RAG script (`rag.py`)

Create `rag.py` in the project root:

```bash
cat > rag.py << 'EOF'
import os
from typing import List, Dict, Any

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from dotenv import load_dotenv

load_dotenv()

...

if __name__ == "__main__":
    main()
EOF
```

Smoke test:

```bash
python rag.py --index
python rag.py --ask "Which machine is better for local LLM RAG workloads?"
```

---

## 8. Ingest Psychology 2e PDF (OER foundation)

1. Place `Psychology2e_WEB.pdf` into `pdf/`:

```bash
mv /path/to/Psychology2e_WEB.pdf pdf/Psychology2e_WEB.pdf
```

2. Create PDF ingester `ingest_pdf.sh`:

```bash
cat > ingest_pdf.sh << 'EOF'
import os
from typing import List, Dict

from pypdf import PdfReader
from rag import index_documents

...

if __name__ == "__main__":
    main()
EOF
```

3. Create `ingest_pdf.sh` shell file:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

...

echo "Ingesting $PDF_PATH with source prefix '$SOURCE_PREFIX'..."
python ingest_pdf.py --pdf "$PDF_PATH" --source-prefix "$SOURCE_PREFIX"
EOF
```

4. Make it executable:
```bash
chmod +x ingest_pdf.sh
```

Usage:

```bash
cd /path/to/my/projects/llm-rag
./ingest_pdf.sh
# It will prompt: Enter PDF filename under pdf/:
# e.g.: Principles_of_Social_Psychology.pdf
```

This seeds your RAG with a full, intentional OER textbook, aligned with your goals and interests, not just random news.

---

## 9. Using the system

From the project root with venv active:

```bash
# General query
python rag.py --ask "How do power dynamics influence behavior in groups?"

# More specific
python rag.py --ask "Explain different bases of social power and how they affect relationships."
```

## 10. HTTP API server and macOS service

To use this RAG from other devices (Windows laptop, iPad, iPhone), expose it as a small HTTP API running on the macOS and keep it running in the background.

### 10.1 Install Dependencies

From the project root:

```bash
cd ~/projects/llm-rag
source .venv/bin/activate
python -m pip install fastapi uvicorn jinja2 python-multipart qdrant-client ollama httpx pydantic
```

### 10.2 Create the API server (`api_server.py`)

Create `api_server.py` in the project root:

```bash
cat > api_server.py << 'EOF'
from fastapi import FastAPI, Request, Form
...
EOF
```

Test it manually:

```bash
source .venv/bin/activate
python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
```

From another machine on your LAN (substitute your Mac's IP):

```bash
curl -X POST "http://MAC_OS_IP:8000/rag" \
  -H "Content-Type: application/json" \
  -d '{"question": "How does knowledge influence behavior in groups?"}'
```

You should receive a JSON response with `answer` and `contexts`.

### 10.3 Shell script to run the API server

Create `run_api_server.sh`:

```bash
cat > run_api_server.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
...
EOF
```

Make it executable:

```bash
chmod +x run_api_server.sh
```

You can now start the server manually with:

```bash
./run_api_server.sh
```

### 10.4 macOS launchd service (auto-start on login)

macOS uses `launchd` instead of systemd to run background services.

Create `~/Library/LaunchAgents/com.localragtext.api.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.localragtext.api</string>
    ...
  </dict>
</plist>
```

Load and start the agent:

```bash
launchctl load ~/Library/LaunchAgents/com.localragtext.api.plist
launchctl start com.localragtext.api
launchctl list | grep com.localragtext.api # displays the PID (Process ID) of the job if it is running
```

---

The API server will now:

- Start automatically when you log into the Mac.
- Restart if it exits unexpectedly.
- Listen on `http://<Mac-Ip>:8000/rag` for POST requests from any device on your network.

This turns your purpose???built, goal???aligned RAG into a small, always???on service you can reach from other devices (Windows, iPad, or iPhone), not drifting into a noisy, generic, ever???changing news feed.

---

Online Public Resources:

- https://openstax.org/
- https://open.umn.edu/
