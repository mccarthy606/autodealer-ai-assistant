"""Launch autodealer locally with embedded Postgres (pgserver) + fakeredis."""
import sys, os, io, subprocess, time, signal

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT)

print("[1/3] Starting embedded PostgreSQL...")
import pgserver
pgdata = os.path.join(PROJECT, ".pgdata")
pg = pgserver.get_server(pgdata, cleanup_mode="stop")
pg_uri = pg.get_uri()
print(f"  Postgres: {pg_uri}")

# Create database 'autodealer'
import psycopg2
from urllib.parse import urlparse
parsed = urlparse(pg_uri)
# Connect to default db to create autodealer
conn = psycopg2.connect(pg_uri)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT 1 FROM pg_database WHERE datname='autodealer'")
if not cur.fetchone():
    cur.execute("CREATE DATABASE autodealer")
    print("  Created database 'autodealer'")
else:
    print("  Database 'autodealer' exists")
cur.close()
conn.close()

# Build URL for autodealer db
db_url = f"postgresql://{parsed.username or 'postgres'}@{parsed.hostname}:{parsed.port}/autodealer"
print(f"  DB URL: {db_url}")

os.environ["DATABASE_URL"] = db_url
os.environ["REDIS_URL"] = "redis://localhost:6379/0"  # fakeredis handles this in-process
os.environ["LLM_ENABLED"] = "false"

print("[2/3] Running alembic migrations...")
try:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], 
                   cwd=PROJECT, timeout=30, check=True)
    print("  Migrations applied")
except Exception as e:
    print(f"  Migration warning: {e}")

print("[3/3] Starting uvicorn on port 8000...")
print("=" * 50)
print("  App: http://localhost:8000")
print("  Docs: http://localhost:8000/docs")
print("  Admin: http://localhost:8000/admin/ui")
print("=" * 50)

proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
    cwd=PROJECT
)

def shutdown(sig, frame):
    print("\nShutting down...")
    proc.terminate()
    pg.cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

proc.wait()
