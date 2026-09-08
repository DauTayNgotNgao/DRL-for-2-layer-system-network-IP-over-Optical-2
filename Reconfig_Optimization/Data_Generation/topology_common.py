# Noi dung/Muc dich:
# File cau noi de cac script co the import topology_common tu goc Data_Generation.
# Phan cai dat chinh dang nam trong Topology/Generate/topology_common.py.

import importlib.util
from pathlib import Path


_IMPL_PATH = Path(__file__).resolve().parent / "Topology" / "Generate" / "topology_common.py"
_SPEC = importlib.util.spec_from_file_location("_topology_common_impl", _IMPL_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load topology helper implementation from {_IMPL_PATH}")

_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

for _NAME in dir(_MODULE):
    if not _NAME.startswith("_"):
        globals()[_NAME] = getattr(_MODULE, _NAME)
