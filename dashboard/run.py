import sys
import argparse
from pathlib import Path

# Make the 'api' package importable from inside dashboard/
sys.path.insert(0, str(Path(__file__).parent.resolve()))

def main():
    parser = argparse.ArgumentParser(description="Research Dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    import uvicorn
    uvicorn.run("api.app:app", host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()
