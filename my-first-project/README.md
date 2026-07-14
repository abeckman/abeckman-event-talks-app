# Event-Driven Pipeline and CLI News Tools

This repository is a multi-purpose codebase featuring an event-driven serverless document processing pipeline for Google Cloud, paired with lightweight command-line feed tools for Google News in both JavaScript and Python.

## Repository Structure

```
.
├── google-cloud-serverless-app/  # Serverless Event-Driven Document Pipeline
│   ├── deploy/                   # Resource provisioning scripts (setup/teardown)
│   ├── processor/                # Python + Flask Cloud Run processor
│   ├── schema/                   # BigQuery schema configuration
│   └── README.md                 # Detailed pipeline documentation
├── demo_bad_code.py              # Pitfalls demo (unsafe indexing, blocking IO)
├── gnews.js                      # Node.js Google News RSS CLI Client
├── gnews.py                      # Python Google News RSS CLI Client
├── package.json                  # Node dependency definition
└── README.md                     # Repository overview (this file)
```

---

## 1. Google News CLI Tool

A lightweight client to fetch, parse, and colorize the latest articles from Google News RSS feeds. Available in both JS and Python flavors.

### JavaScript Version (`gnews.js`)

#### Prerequisites & Setup:
Ensure you have [Node.js](https://nodejs.org/) installed, then install the dependencies:
```bash
npm install
```

#### Usage:
Run the script using `node` or the npm start script:
```bash
# Get top stories (default)
node gnews.js

# Fetch by topic (world, technology, science, health, etc.)
node gnews.js -t technology

# Search for custom keywords
node gnews.js -s "artificial intelligence" --limit 5
```

### Python Version (`gnews.py`)

#### Prerequisites:
Runs with standard Python 3 (no third-party dependencies required, as it uses built-in `urllib` and `xml.etree`).

#### Usage:
```bash
# Get top stories
python gnews.py

# Fetch by topic
python gnews.py --topic science

# Search and limit output count
python gnews.py --search "superconductivity" --limit 3
```

---

## 2. Serverless Document Processing Pipeline

Located in the [google-cloud-serverless-app](./google-cloud-serverless-app/) directory, this is a fully serverless, event-driven pipeline on Google Cloud Platform (GCP).

### Flow Architecture:
1. **Upload:** A user or client uploads a document (PDF, TXT, image, etc.) to a Google Cloud Storage ingestion bucket.
2. **Trigger:** GCS fires an `OBJECT_FINALIZE` event notification to a Pub/Sub topic.
3. **Execution:** Pub/Sub pushes the notification to a Python Flask service running on Cloud Run.
4. **Processing:** The Cloud Run service downloads the file, performs metadata extraction (language detection, token-based tags, page count, and confidence scores), and streams the result into BigQuery.
5. **Storage:** Structured metadata resides in BigQuery for low-latency analytical queries.

For detailed setup, configuration, and testing commands, see the [Pipeline README](./google-cloud-serverless-app/README.md).

---

## 3. Demo Code (`demo_bad_code.py`)

A script demonstrating typical programming anti-patterns including:
- **Unsafe dictionary access:** Likely to raise `TypeError` when handling empty/missing returns.
- **Blocking delay loops:** Synchronously blocking processes (`time.sleep`) instead of utilizing async handlers.
- **Float arithmetic for currency:** Why raw floating-point operations should not be used for precision-critical calculations.
