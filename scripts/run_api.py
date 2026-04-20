import sys
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="127.0.0.1", port=8010, reload=False)
