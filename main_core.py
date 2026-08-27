"""
Entry point for LYNS Core — full editor minus "The Project" section.
Sets ECTOFORM_EDITION=core then delegates to main.main().
"""
import os
os.environ["ECTOFORM_EDITION"] = "core"

from main import main

if __name__ == "__main__":
    main()
