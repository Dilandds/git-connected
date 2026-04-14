"""
Entry point for the ECTOFORM Education edition.
Sets ECTOFORM_EDITION=education then delegates to main.main().
"""
import os
os.environ["ECTOFORM_EDITION"] = "education"

from main import main

if __name__ == "__main__":
    main()
