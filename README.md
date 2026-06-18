# Fact-Check Agent

A "Truth Layer" web app. Upload a marketing PDF; it extracts factual claims
(stats, dates, financial/technical figures), cross-references each against live
web data, and flags them as **Verified**, **Inaccurate**, or **False** — with
the correct real fact when something is wrong.

## How it works

1. **Extract** — pull text from the PDF (`pypdf`).
2. **Identify claims** — Claude pulls out self-contained, checkable claims.
3. **Verify** — each claim is searched on the live web (Tavily).
4. **Judge** — Claude rules on each claim against the evidence and supplies the
   correct figure when it's outdated or wrong.

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export TAVILY_API_KEY=tvly-...
streamlit run app.py
```

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub.
2. On https://share.streamlit.io → **New app** → point at `app.py`.
3. In **Settings → Secrets**, add:

   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   TAVILY_API_KEY = "tvly-..."
   ```

4. Deploy. You'll get a public `https://<name>.streamlit.app` URL.

> Tavily offers a free tier (1,000 searches/mo). Any web-search API works —
> swap the `web_search()` function if you prefer SerpAPI / Brave / Bing.

## Files

- `app.py` — the whole app (extract → search → verify → report).
- `requirements.txt` — dependencies.
