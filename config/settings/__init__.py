import os


if os.getenv("VERCEL"):
    from .prod import *
else:
    from .dev import *
