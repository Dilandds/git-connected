"""
Entry point for LYNS Lite — the supplier-facing companion app.
Sets ECTOFORM_EDITION=lite then delegates to main.main().
"""
import os
os.environ["ECTOFORM_EDITION"] = "lite"

from main import main

if __name__ == "__main__":
    main()
