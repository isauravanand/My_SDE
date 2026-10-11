# Backend

## Run locally

1. Create a PostgreSQL database named `my_sde`.
2. Copy `.env.example` to `.env` and update `DATABASE_URL` for your database.
3. From this directory, install dependencies and start the API:

	```powershell
	uv sync
	uv run uvicorn app.main:app --reload
	```

The API docs are at `http://127.0.0.1:8000/docs`. `GET /health` checks the API;
`GET /health/db` runs `SELECT 1` against PostgreSQL.
