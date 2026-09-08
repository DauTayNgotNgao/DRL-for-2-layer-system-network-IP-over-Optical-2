# Noi dung/Muc dich:
# Pipeline sinh topology bang mot lenh. File nay chay cac buoc sinh nodes,
# physical links, mappings, candidate paths, slots va baseline lightpaths theo
# dung thu tu phu thuoc du lieu.

import runpy
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


PIPELINE = [
    "Topology/Generate/Nodes/Generate_Optical_Nodes.py",
    "Topology/Generate/Nodes/Generate_IP_Nodes.py",
    "Topology/Generate/Nodes/Generate_CDN_Nodes.py",
    "Topology/Generate/Nodes/Generate_End_User_Nodes.py",
    "Topology/Generate/Links/Optical_Links.py",
    "Topology/Generate/Links/IP_Links.py",
    "Topology/Mapping/(IP_Nodes) - (Optical_Nodes).py",
    "Topology/Mapping/(CDN) - (IP_Nodes).py",
    "Topology/Mapping/(End_user) - (IP_Nodes).py",
    "Topology/Generate/Links/K_shortest_path.py",
    "Topology/Generate/Slots/Generate_Optical-Fiber-Slots.py",
    "Topology/Generate/Links/IP_Lightpaths.py",
    "Topology/Generate/Links/Optical_Lightpaths.py",
]


def main() -> None:
    for relative_script in PIPELINE:
        script_path = BASE_DIR / relative_script
        print(f"\n=== Running {relative_script} ===")
        runpy.run_path(str(script_path), run_name="__main__")


if __name__ == "__main__":
    main()
