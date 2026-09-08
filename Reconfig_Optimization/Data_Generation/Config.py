# Noi dung/Muc dich:
# File cau hinh trung tam cho qua trinh sinh topology gia lap. Sua file nay
# de dieu khien so luong node/link, capacity, random seed va duong dan output.

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
TOPOLOGY_OUTPUT_DIR = BASE_DIR / "Output" / "Topology"
TRAFFICT_OUTPUT_DIR = BASE_DIR / "Output" / "Traffict"

NODES_OUTPUT_DIR = TOPOLOGY_OUTPUT_DIR / "Nodes"
LINKS_OUTPUT_DIR = TOPOLOGY_OUTPUT_DIR / "Links"
MAPPING_OUTPUT_DIR = TOPOLOGY_OUTPUT_DIR / "Mapping"
PATHS_OUTPUT_DIR = TOPOLOGY_OUTPUT_DIR / "Candidate_Paths"
SLOTS_OUTPUT_DIR = TOPOLOGY_OUTPUT_DIR / "Slots"
LIGHTPATH_OUTPUT_DIR = TOPOLOGY_OUTPUT_DIR / "Lightpaths"

H_TRAFFICT_OUTPUT_DIR = TRAFFICT_OUTPUT_DIR / "Hypergiants_Trafficts"
BG_TRAFFICT_OUTPUT_DIR = TRAFFICT_OUTPUT_DIR / "Background_Trafficts"
INITIAL_ALL_TRAFFICT_OUTPUT_DIR = TRAFFICT_OUTPUT_DIR / "Initial_All_Traffict"


# Kha nang tai lap ket qua.
RANDOM_SEED = 42


# Kich thuoc mang synthetic.
NUM_OPTICAL_NODES = 32
NUM_IP_NODES = 32
NUM_END_USER_NODES = 30


# So link. Optical physical links duoc luu dang undirected fiber.
# 125 undirected fibers tuong duong 250 directed arcs, mean in-degree/out-degree
# tren directed view la 250 / 32 = 7.8125.
TARGET_OPTICAL_DIRECTED_LINKS = 250
NUM_OPTICAL_LINKS = TARGET_OPTICAL_DIRECTED_LINKS // 2
NUM_IP_LINKS = 45


# Mat phang toa do dung cho nearest-neighbor mapping.
AREA_WIDTH = 1000.0
AREA_HEIGHT = 1000.0
IP_COLLOCATION_JITTER = 8.0
CDN_LOCATION_JITTER = 40.0
END_USER_LOCATION_JITTER = 80.0


# Mo hinh capacity optical/IP, bam theo setting don gian hoa cua paper.
LIGHTPATH_CAPACITY_GBPS = 100
FIBER_CAPACITY_LIGHTPATHS = 100
IP_ROUTER_TRANSCEIVERS = 100
MAX_IP_LINK_UTILIZATION = 0.50
K_SHORTEST_PATHS = 10


# CDN peering capacities duoc sinh trong khoang dong nay.
PEERING_CAPACITY_MIN_GBPS = 800
PEERING_CAPACITY_MAX_GBPS = 1600
PEERING_CAPACITY_STEP_GBPS = 100


# End-user nodes dai dien cho cac cum access/user area da aggregate.
USER_GROUP_SIZE_MIN = 50_000
USER_GROUP_SIZE_MAX = 2_000_000
END_USER_DEMAND_SCALE_MIN_GBPS = 20
END_USER_DEMAND_SCALE_MAX_GBPS = 300


# Hyper-giants va so peering site cua moi hyper-giant/CDN.
NUM_HYPERGIANTS = 5
HYPERGIANT_IDS = [f"hg_{index}" for index in range(NUM_HYPERGIANTS)]
CDN_PEERINGS_PER_HYPERGIANT = 2
NUM_CDN_NODES = len(HYPERGIANT_IDS) * CDN_PEERINGS_PER_HYPERGIANT


# Initial traffic generation.
INITIAL_BG_DEMAND_COUNT = 80
INITIAL_H_DEMAND_COUNT = 270
BG_TRAFFICT_MIN_GBPS = 5
BG_TRAFFICT_MAX_GBPS = 40
H_TRAFFICT_MIN_GBPS = 5
H_TRAFFICT_MAX_GBPS = 30
RANDOM_ROUTE_ATTEMPTS = 64


# Dynamic traffic generation. Load factor nam trong [0, 1]:
# 0.2 = thoang, 0.5 = binh thuong, 1.0 = tac nang.
DYNAMIC_TIME_HORIZON = 100.0
DYNAMIC_LOAD_FACTOR = 0.5
DYNAMIC_H_TRAFFIC_SHARE = 0.70
MEAN_CONNECTION_BANDWIDTH_GBPS = 10.0
BANDWIDTH_WEIBULL_CV = 0.30
MEAN_CONNECTION_DURATION = 10.0
MIN_CONNECTION_DURATION = 5.0
MAX_CONNECTION_DURATION = 15.0
DYNAMIC_FULL_LOAD_ARRIVAL_RATE = (
    TARGET_OPTICAL_DIRECTED_LINKS / MEAN_CONNECTION_DURATION
)


# Ten file output.
OPTICAL_NODES_FILE = NODES_OUTPUT_DIR / "optical_nodes.csv"
IP_NODES_FILE = NODES_OUTPUT_DIR / "ip_nodes.csv"
CDN_NODES_FILE = NODES_OUTPUT_DIR / "cdn_nodes.csv"
END_USER_NODES_FILE = NODES_OUTPUT_DIR / "end_user_nodes.csv"

OPTICAL_LINKS_FILE = LINKS_OUTPUT_DIR / "optical_physical_links.csv"
IP_LINKS_FILE = LINKS_OUTPUT_DIR / "initial_ip_links.csv"

CDN_IP_MAPPING_FILE = MAPPING_OUTPUT_DIR / "cdn_ip_peering.csv"
END_USER_IP_MAPPING_FILE = MAPPING_OUTPUT_DIR / "end_user_ip_mapping.csv"
IP_OPTICAL_MAPPING_FILE = MAPPING_OUTPUT_DIR / "ip_optical_collocation.csv"

CANDIDATE_OPTICAL_PATHS_FILE = PATHS_OUTPUT_DIR / "candidate_optical_paths.csv"
OPTICAL_FIBER_SLOTS_FILE = SLOTS_OUTPUT_DIR / "optical_fiber_slots.csv"

BASELINE_IP_LIGHTPATHS_FILE = LIGHTPATH_OUTPUT_DIR / "baseline_ip_lightpaths.csv"
BASELINE_OPTICAL_LIGHTPATHS_FILE = LIGHTPATH_OUTPUT_DIR / "baseline_optical_lightpaths.csv"

BG_INITIAL_DEMANDS_FILE = BG_TRAFFICT_OUTPUT_DIR / "bg_initial_demands.csv"
BG_INITIAL_ROUTING_FILE = BG_TRAFFICT_OUTPUT_DIR / "bg_initial_routing.csv"
BG_INITIAL_IP_LIGHTPATH_LOADS_FILE = BG_TRAFFICT_OUTPUT_DIR / "bg_initial_ip_lightpath_loads.csv"
BG_INITIAL_RESOURCE_USAGE_FILE = BG_TRAFFICT_OUTPUT_DIR / "bg_initial_resource_usage.csv"

H_INITIAL_DEMANDS_FILE = H_TRAFFICT_OUTPUT_DIR / "h_initial_demands.csv"
H_INITIAL_ROUTING_FILE = H_TRAFFICT_OUTPUT_DIR / "h_initial_routing.csv"
H_INITIAL_PEERING_LOADS_FILE = H_TRAFFICT_OUTPUT_DIR / "h_initial_peering_loads.csv"
H_INITIAL_IP_LIGHTPATH_LOADS_FILE = H_TRAFFICT_OUTPUT_DIR / "h_initial_ip_lightpath_loads.csv"
H_INITIAL_RESOURCE_USAGE_FILE = H_TRAFFICT_OUTPUT_DIR / "h_initial_resource_usage.csv"

ALL_INITIAL_DEMANDS_FILE = INITIAL_ALL_TRAFFICT_OUTPUT_DIR / "all_initial_demands.csv"
ALL_INITIAL_ROUTING_FILE = INITIAL_ALL_TRAFFICT_OUTPUT_DIR / "all_initial_routing.csv"
ALL_INITIAL_IP_LIGHTPATH_LOADS_FILE = (
    INITIAL_ALL_TRAFFICT_OUTPUT_DIR / "all_initial_ip_lightpath_loads.csv"
)
ALL_INITIAL_RESOURCE_USAGE_FILE = (
    INITIAL_ALL_TRAFFICT_OUTPUT_DIR / "all_initial_resource_usage.csv"
)

BG_DYNAMIC_TRAFFIC_MATRIX_FILE = BG_TRAFFICT_OUTPUT_DIR / "bg_dynamic_traffic_matrix.csv"
BG_DYNAMIC_REQUESTS_FILE = BG_TRAFFICT_OUTPUT_DIR / "bg_dynamic_requests.csv"

H_DYNAMIC_TRAFFIC_MATRIX_FILE = H_TRAFFICT_OUTPUT_DIR / "h_dynamic_traffic_matrix.csv"
H_DYNAMIC_REQUESTS_FILE = H_TRAFFICT_OUTPUT_DIR / "h_dynamic_requests.csv"

ALL_DYNAMIC_REQUESTS_FILE = TRAFFICT_OUTPUT_DIR / "all_dynamic_requests.csv"
