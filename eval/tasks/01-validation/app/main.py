from fastapi import FastAPI

app = FastAPI()
USERS = [{"id": i, "name": f"user{i}"} for i in range(1, 26)]


@app.get("/users")
def list_users(page: int = 1, limit: int = 10):
    """Return a paginated list of users.

    Query parameters:
    - **page**: page number (1-based). Defaults to 1. Values less than 1 are treated as 1.
    - **limit**: number of items per page. Defaults to 10. Values less than 1 are treated as 1.
    """
    # Ensure sensible defaults for non-positive inputs
    page = max(page, 1)
    limit = max(limit, 1)

    start = (page - 1) * limit
    end = start + limit
    return USERS[start:end]
