# LLM Configuration

Set one of these backends via environment variables:

- `LLM_BACKEND=mock` (default, no API calls)
- `LLM_BACKEND=openrouter` with `OPENROUTER_API_KEY`
- `LLM_BACKEND=google` with `GOOGLE_API_KEY`

Optional:
- `OPENROUTER_MODEL` (default: openai/gpt-4o-mini)
- `GOOGLE_MODEL` (default: gemini-1.5-flash)
