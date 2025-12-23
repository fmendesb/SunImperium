# Sun Imperium Console (Streamlit + Supabase)

Canon UI:
- **The Silver Council**: Dashboard, Reputation, Legislation, Diplomacy, Infrastructure
- **Moonblade Guild**: Military + War Simulator
- **Dawnbreakers**: Intelligence

## 1) Set up Supabase
1. Open Supabase SQL editor.
2. Run `sql/schema_v1.sql`.
3. (Optional) Seed tables from your Excel later.

## 2) Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 3) Streamlit Community Cloud
- Create a GitHub repo with this folder.
- Deploy on Streamlit Cloud.
- In **Settings → Secrets**, paste values based on `.streamlit/secrets.toml.template`.

## Notes
- **No auth** for v1. Only dangerous actions are gated by `DM_PASSWORD` (Advance Week, Apply War Results).
- **Undo** is per-category and uses `action_logs`.
- **Advance Week** currently applies upkeeps automatically and allows manual income until the Market module is wired.
