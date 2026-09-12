"""`python -m zeg.runtime` — start the model process."""

import sys

from .server import main

if __name__ == "__main__":
    sys.exit(main())
