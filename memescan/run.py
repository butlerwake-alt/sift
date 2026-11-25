"""Scan and audit every run. Grade on the hour, or when --grade is passed."""

import sys
from datetime import datetime, timezone

import audit
import grade
import scan


def main(argv):
    scan.main()
    audit.main()
    minute = datetime.now(timezone.utc).minute
    if "--grade" in argv or minute < 10:
        grade.main()
    else:
        print("memescan run: grade waits for the hourly tick.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
