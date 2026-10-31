# PolicyBot evaluation

`dataset.json` contains 10 hand-written, answerable policy questions covering leave, travel, IT security, and conduct. Evaluation runs only the hybrid retrieval with Groq reranking.

## Add API keys

Open `D:\Policybot\.env` in VS Code. Add or update these lines without quotes, keeping the values private:

```text
GROQ_API_KEY=your_groq_key
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_PROJECT=policybot
ANSWER_MODEL=openai/gpt-oss-120b
SMALL_MODEL=openai/gpt-oss-20b
```

Create a Groq API key at [Groq Console](https://console.groq.com/keys). Create a LangSmith API key in [LangSmith](https://smith.langchain.com/) under Settings → API Keys. Do not paste either key into chat or commit `.env`.

## Upload the sample policies

Start the app, sign in with the seeded admin, and upload these five files from `D:\Policybot\tests\fixtures\policybot_samples\documents` in order:

1. `01_leave_policy_v1.docx`
2. `01_leave_policy_v2.docx` (updates the leave document to version 2)
3. `02_travel_expense_policy.pdf`
4. `03_it_security_policy.docx`
5. `04_code_of_conduct.pdf`

The uploader indexes the files and clears answer cache after every change.

## Start/rebuild the API

From PowerShell in `D:\Policybot`:

```powershell
docker compose up --build -d api
```

## Install evaluation dependencies and check setup

```powershell
& "D:\Policybot\.venv\Scripts\python.exe" -m pip install -r "D:\Policybot\requirements-eval.txt"
& "D:\Policybot\.venv\Scripts\python.exe" "D:\Policybot\eval\run_deepeval.py" --dry-run
```

## Run the five metrics

Run the 10 questions with hybrid retrieval and Groq reranking. The report includes all five metric averages and latency/cache results:

```powershell
& "D:\Policybot\.venv\Scripts\python.exe" "D:\Policybot\eval\run_deepeval.py"
```

The script asks for the seeded admin email/password in the terminal; the password is entered without echo. Results are written to `D:\Policybot\eval\results`. DeepEval's judge calls use Groq `openai/gpt-oss-20b`; LangChain calls are traced to the configured LangSmith project.
