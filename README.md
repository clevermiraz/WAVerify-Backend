# WAVerify - Backend

WAVerify is a simple and efficient service that allows users to check whether a given phone number is registered on WhatsApp. 

This repository contains the backend component, built with **FastAPI**, **PostgreSQL**, and **Redis**.

## Tech Stack
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python)
- **Database**: PostgreSQL (with SQLAlchemy and Alembic for migrations)
- **Cache**: Redis
- **Containerization**: Docker & Docker Compose

---

## Quick Start Guide

### Prerequisites
Make sure you have the following installed on your machine:
- [Python 3.10+](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

### 1. Environment Setup
Clone the repository and navigate to the project directory.

Copy the example environment variables file and configure it:
```bash
cp .env.example .env
```
Open the `.env` file and generate a `SECRET_KEY`. You can generate a secure key using your terminal:
```bash
openssl rand -hex 32
```
Paste the generated output as the `SECRET_KEY` in your `.env` file.

### 2. Running with Docker (Recommended)
You can easily spin up the backend, database, and Redis cache using Docker Compose:

```bash
docker-compose up --build
```
*Note: If the `docker-compose.yml` expects a specific build context, make sure you're running it from the correct directory level.*

The API will now be accessible at `http://localhost:8000`.
You can view the interactive API documentation (Swagger UI) at `http://localhost:8000/docs`.

### 3. Running for Local Development (Without Docker for the API)
If you prefer to run the FastAPI app locally for development while using Docker for the databases:

1. **Start the databases**:
   You can start just PostgreSQL and Redis using Docker:
   ```bash
   docker-compose up postgres redis -d
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```

5. **Start the development server**:
   ```bash
   uvicorn app.main:app --reload
   ```

The application will be running at `http://localhost:8000`.

### 4. Running Tests

The test suite relies on a real PostgreSQL and Redis database. The tests automatically mock the WhatsApp provider for safe execution.

1. **Start the database containers** (if not already running):
   ```bash
   docker-compose up postgres redis -d
   ```

2. **Create the test database**:
   Run the following command to create an isolated database for tests (so it doesn't overwrite your local development data):
   ```bash
   docker-compose exec postgres psql -U waverify -c 'CREATE DATABASE waverify_test;'
   ```

3. **Run the test suite**:
   If your `docker-compose.yml` or `.env` maps Postgres to port `5433` and Redis to port `6380`, you must pass those URLs when running tests:
   ```bash
   TEST_DATABASE_URL="postgresql+psycopg://waverify:waverify@localhost:5433/waverify_test" \
   TEST_REDIS_URL="redis://localhost:6380/15" \
   pytest tests/
   ```

---
## Project Structure
- `app/`: The core FastAPI application (routes, models, schemas).
- `alembic/`: Database migration scripts.
- `tests/`: Test cases.
- `scripts/`: Utility scripts.
