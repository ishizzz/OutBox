# OutBox

A smart job outreach automation tool that drafts personalized cold emails with AI, verifies claims against your resume, and sends them to recruiters. Built for efficient, targeted job searching.

## Features

- **AI-Powered Drafting**: Uses OpenAI (GPT-4o) to write compelling, tailored outreach emails based on your resume and target company/role
- **Claims Verification**: Automatically fact-checks every claim in the draft against your resume to prevent embellished or false statements from reaching recruiters
- **Bulk Import**: Import candidate targets via CSV for batch processing
- **Live Search**: Filter your pipeline by company name, contact name, or role
- **Bulk Automation**: 
  - Generate drafts for all pending targets at once (with safety: flagged drafts held for review)
  - Send multiple approved emails with one click
- **Review & Edit**: Review each draft, edit claims, and approve before sending
- **Pipeline Tracking**: Track targets through stages: queued → drafted → sent → replied
- **Follow-up Reminders**: Automatic flagging of emails that need follow-up (7+ days without reply)

## Tech Stack

- **Backend**: Flask (Python web framework)
- **Database**: SQLite
- **AI**: OpenAI API (GPT-4o for drafting, GPT-4o-mini for claims validation)
- **Email**: Gmail SMTP with App Passwords
- **Frontend**: HTML/CSS/vanilla JavaScript

## Setup

### Prerequisites

- Python 3.8+
- OpenAI API key
- Gmail account with App Password configured (for SMTP)
- Your resume as PDF or TXT file

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/OutBox.git
   cd OutBox
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root with your configuration:
   ```
   OPENAI_API_KEY=sk-...
   DRAFT_MODEL=gpt-4o
   VALIDATE_MODEL=gpt-4o-mini
   GMAIL_ADDRESS=your-email@gmail.com
   GMAIL_APP_PASSWORD=your-16-char-app-password
   RESUME_PATH=~/Downloads/your_resume.pdf
   YOUR_NAME=Your Full Name
   ```

   **Note**: 
   - Get your OpenAI API key from [platform.openai.com](https://platform.openai.com)
   - Generate a Gmail App Password: Google Account → Security → 2-Step Verification → App passwords (select "Mail" and "Windows Computer")
   - Resume can be PDF or TXT; must contain at least 200 characters of extractable text

4. Run the application:
   ```bash
   python app.py
   ```

5. Open your browser to `http://127.0.0.1:5000`

## Usage

### Workflow

1. **Add Targets**: Manually add individual targets or bulk import via CSV
2. **Generate Drafts**: Click "Generate draft" for any target (or "Generate & send all pending" for batch)
3. **Review**: View the draft, see which claims are verified against your resume
4. **Edit & Refine**: Make any changes to the subject or body before sending
5. **Send**: Approve and send, or bulk-send multiple approved drafts
6. **Track**: Monitor status of sent emails and mark replies

### Bulk Import CSV Format

Create a CSV file with these columns (all required except `posting_url` and `posting_text`):

```csv
company,role,contact_name,contact_title,contact_email,posting_url,posting_text
Acme Corp,ML Engineer,Jane Doe,Hiring Manager,jane@acme.com,https://jobs.acme.com/ml-eng,
TechCo,Senior Engineer,Bob Smith,Recruiter,recruiter@techco.com,,Optional full job posting text here
```

Then go to the pipeline and click "Bulk import" → select your CSV file.

### Safety Features

- **Claims Checking**: Every factual statement about you is verified against your resume. Unverified claims are flagged with a red badge and excluded from bulk-send by default
- **Confirmation Dialogs**: Important actions (bulk generate, bulk send) require explicit confirmation with a list of affected companies
- **Manual Review**: You can always review and edit any draft before sending
- **Per-Target Error Handling**: If one email fails to send, the batch continues without blocking

## Project Structure

```
OutBox/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── .env                   # Configuration (not in git)
├── .gitignore            # Git ignore rules
├── README.md             # This file
├── outreach.db           # SQLite database
├── resume_*.pdf          # Your resume (not in git)
├── static/
│   └── style.css         # Application styling
├── templates/
│   ├── base.html         # Layout template
│   ├── index.html        # Pipeline view
│   ├── review.html       # Draft review & editing
│   ├── target_form.html  # Add target form
│   └── ...
└── outreach/
    ├── __init__.py
    ├── db.py             # Database operations
    ├── drafter.py        # AI drafting & claims checking
    ├── mailer.py         # Email sending
    ├── research.py       # Job posting fetching
    └── resume.py         # Resume loading
```

## How It Works

### Drafting Process

1. **Load Resume**: Reads your resume text
2. **Fetch Posting** (optional): Attempts to scrape job posting from URL (works best with Greenhouse, Lever, Ashby; LinkedIn & Workday usually block)
3. **Generate Draft**: Sends resume + company/role + posting to GPT-4o with strict instructions to only claim things from your resume
4. **Verify Claims**: Second LLM pass extracts all factual claims and checks them against your resume text
5. **Flag Issues**: Any unsupported claims are highlighted for you to fix before sending

### Email Sending

- Emails are sent via Gmail SMTP with your resume attached
- Each target's contact info, name, and title are used to personalize the greeting
- Drafts are stored in the database for audit trail

## Configuration

All configuration is via environment variables in `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |
| `DRAFT_MODEL` | No | Model for drafting (default: `gpt-4o`) |
| `VALIDATE_MODEL` | No | Model for claims validation (default: `gpt-4o-mini`) |
| `GMAIL_ADDRESS` | Yes | Gmail address to send from |
| `GMAIL_APP_PASSWORD` | Yes | Gmail App Password (16 chars) |
| `RESUME_PATH` | Yes | Path to your resume (PDF or TXT) |
| `YOUR_NAME` | No | Your full name (used in drafts) |

## Troubleshooting

### "Could not fetch the posting URL"
Some job boards (LinkedIn, Workday, Indeed) block automated fetching. Copy and paste the full job description into the "Job posting text" field instead.

### "Resume text is suspiciously short"
If your PDF is a scanned image, convert it to a text-based PDF first, or export as TXT. Alternatively, point `RESUME_PATH` at a `.txt` version.

### "GMAIL_ADDRESS or GMAIL_APP_PASSWORD missing"
Make sure both are set in `.env`. Use an [App Password](https://myaccount.google.com/apppasswords), not your regular Gmail password.

### "Send failed" after bulk generate
Check that your Gmail credentials are correct and 2-Step Verification is enabled. If you just created an app password, it may take a few minutes to activate.

## Development

### Running Tests

(Currently no automated tests; manual testing via Flask test client)

### Extending

- Add new LLM models by editing `DRAFT_MODEL` / `VALIDATE_MODEL` in `.env`
- Customize drafting instructions in `outreach/drafter.py` (see `DRAFT_SYSTEM` prompt)
- Change job board posting scrapers in `outreach/research.py`

## Database

OutBox uses SQLite for simplicity. The database (`outreach.db`) stores:
- **targets**: Company, role, contact info, posting URLs, status
- **drafts**: Generated emails, subject, body, claims verification report

The database is created automatically on first run and migrations are applied as needed.

## License

MIT

## Author

Built as a personal job search automation tool.

---

**Questions or issues?** Open an issue on GitHub or improve this README with a pull request!
