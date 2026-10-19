
# Company Intelligence Analyzer

An AI-powered Python CLI tool that analyzes a company's public website and recent news to generate structured business intelligence, identify potential operational bottlenecks, and summarize relevant business triggers.

## Overview

The Company Intelligence Analyzer helps users understand a company before an interview, sales conversation, or business meeting.

Given a company URL, the tool:

- Scrapes publicly accessible company webpages.
- Collects recent company-related news using Google News RSS.
- Uses a Large Language Model (LLM) to analyze the collected information.
- Identifies the company's business model and target customer persona.
- Highlights a recent business trigger and explains its relevance.
- Generates a potential operational bottleneck hypothesis.
- Returns structured JSON with execution metadata.

## Features

- **Website Scraping:** Extracts readable text using Requests and BeautifulSoup.
- **Recent News Discovery:** Searches Google News RSS for company-related news.
- **AI-Powered Analysis:** Uses the Groq API to generate business intelligence.
- **Structured JSON Output:** Produces consistent output fields.
- **Execution Metadata:** Records the model used and analysis latency.
- **Report Generation:** Saves generated reports as local JSON files.
- **Environment Configuration:** Keeps API credentials separate from source code.

## Tech Stack

- Python
- Requests
- BeautifulSoup
- Groq API
- Pydantic
- python-dotenv
- uv

## Project Structure

```text
company-intelligence-analyzer/
├── app.py
├── README.md
├── requirements.txt
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
└── reports/
    └── generated_report.json
```

Note: The actual `.env` file and generated reports are excluded from version control.

## Requirements

- Python 3.12 or a compatible Python version
- uv package manager
- Groq API key

## Installation and Setup

### 1. Clone the Repository

Replace `YOUR-USERNAME` with your GitHub username.

```bash
git clone https://github.com/YOUR-USERNAME/company-intelligence-analyzer.git
cd company-intelligence-analyzer
```

### 2. Create a Virtual Environment

```bash
uv venv
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
uv sync
```

Alternatively:

```bash
uv pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

Add your Groq API key to `.env`:

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
```

Get an API key from https://console.groq.com/.

**Important:** Never commit your actual `.env` file or expose your API key publicly.

## Usage

Run the analyzer by providing a company's public website URL:

```bash
uv run python app.py https://stripe.com
```

Replace the example URL with another publicly accessible company website.

The application collects website content, searches recent news, sends the information to the configured LLM, and generates a structured JSON result.

Progress messages appear in the terminal. The result is printed as JSON and saved locally as a report.

## Output Format

The generated JSON follows this structure:

```json
{
  "company_name": "Example Company",
  "analyzed_url": "https://example.com",
  "business_summary": {
    "model": "Description of the company's business model",
    "target_persona": "Description of its target customers"
  },
  "key_business_trigger": {
    "headline": "Recent business development",
    "date_or_timeframe": "2026-10-15",
    "source_relevance": "Why the development matters to the company"
  },
  "operational_bottleneck_hypothesis": "Hypothesis: A potential operational constraint affecting growth or execution.",
  "execution_metadata": {
    "model_used": "openai/gpt-oss-120b",
    "latency_seconds": 2.42
  }
}
```

The values above are illustrative examples, not verified claims about a real company.

## How It Works

1. **Input:** The user provides a company website URL.
2. **Validation:** The application validates the URL before fetching content.
3. **Web Scraping:** Readable text is extracted from the homepage and selected company pages.
4. **News Discovery:** Google News RSS is searched for recent company-related developments.
5. **AI Analysis:** Website content and available news information are passed to the Groq model.
6. **Structured Response:** The model generates the required business intelligence fields.
7. **Report Generation:** The result includes execution metadata and is saved as JSON.

## Operational Bottleneck Hypothesis

The bottleneck is an evidence-informed hypothesis, not a confirmed internal company problem.

For example, rapid expansion might create potential challenges in customer onboarding, customer support, or operational scalability. Such conclusions should be verified through additional research.

## Limitations

- Only publicly accessible webpages can be analyzed.
- Some websites block automated requests or render content dynamically.
- The analyzer may not find every relevant page or news article.
- Google News RSS provides search-result metadata and links; full article access is not guaranteed.
- News headlines and publication dates should be verified against original sources.
- LLM-generated summaries and hypotheses may contain inaccurate or unsupported claims.
- Results depend on website content, available news, model behavior, and API availability.

## Future Improvements

- Add more news sources.
- Improve source verification and citation handling.
- Include direct source URLs in the JSON output.
- Add retries, caching, and improved error handling.
- Add unit tests and JSON validation.
- Build a web interface or API for integration with other applications.

## Security Considerations

- Store API keys in environment variables.
- Keep `.env` out of Git version control.
- Validate URLs and restrict requests to public destinations.
- Avoid sending confidential information to external AI services.
- Treat scraped content and AI-generated results as untrusted data.

## Author

**Ritik Chaudhary**

A Python-based AI project demonstrating web scraping, LLM integration, structured data extraction, and business intelligence automation.
