import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="wishclaim-test-")
os.environ.setdefault("DATA_DIR", _tmp)
