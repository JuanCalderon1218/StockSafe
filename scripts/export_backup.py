"""Create an encrypted portable .ssb file for GitHub Actions artifacts."""
from pathlib import Path
from datetime import datetime, timezone
from app.db import get_db
from app.services.backups import make_encrypted_snapshot


def main():
    target = Path("backups")
    target.mkdir(exist_ok=True)
    encrypted, stats = make_encrypted_snapshot(get_db())
    filename = "StockSafe_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + ".ssb"
    path = target / filename
    path.write_bytes(encrypted)
    print(f"Encrypted snapshot created: {path.name}; documents: {stats['total']}; bytes: {len(encrypted)}")


if __name__ == "__main__":
    main()
