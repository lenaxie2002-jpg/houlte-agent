# Houlte Email Agent - VPS Deploy Version

This is the deployable Flask version of the Houlte Email Marketing Agent.

## Local test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with real keys
python app.py
```

Open: http://localhost:5000

## Production run

```bash
gunicorn app:app --bind 0.0.0.0:5000 --workers 2 --timeout 120
```

## Environment variables

- `ANTHROPIC_API_KEY`: Anthropic key or OpenRouter key used by `/api/claude`
- `OPENROUTER_API_KEY`: OpenRouter key used by `/api/generate-image`
- `MAILCHIMP_API_KEY`: Mailchimp API key
- `MAILCHIMP_DC`: Mailchimp data center, e.g. `us9`
- `FEISHU_WEBHOOK`: Feishu bot webhook
- `APP_ORIGIN`: public origin, e.g. `https://agent.houlte.com`
- `APP_TITLE`: request title for OpenRouter
- `PORT`: default `5000`

## Important security note

Do not commit `.env`. Do not put API keys in the HTML file. Rotate any key that was previously committed or shared.
