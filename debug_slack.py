import sys
from collections import defaultdict
import networkx as nx

from src_hung.main import load_config
from src_hung.model.network import generate_multilayer_topology
from src_hung.model.demand import generate_random_demands
from src_hung.rl.env.env import CrossLayerEnv
from src_hung.rl import config

def main():
    net_cfg = load_config()["network"]
    
    physical_net, ip_graph, ip_to_opt_map = generate_multilayer_topology(
        opt_nodes=net_cfg["opt_nodes"],
        opt_links=net_cfg["opt_links"],
        ip_nodes=net_cfg["ip_nodes"],
        ip_links=net_cfg["ip_links"],
        num_slots=net_cfg["num_slots"],
        lightpath_capacity=net_cfg["lightpath_capacity"],
        seed=42,
    )
    opt_graph = physical_net.graph
    
    # Sử dụng 20 demands giống hệt test run
    demands = generate_random_demands(20, net_cfg["ip_nodes"], 10, 50, 42)
    demand_by_id = {d.id: d for d in demands}
    
    env = CrossLayerEnv(
        physical_net=physical_net,
        ip_graph=ip_graph,
        opt_graph=opt_graph,
        ip_to_opt_map=ip_to_opt_map,
        demands=demands,
        lightpath_capacity=net_cfg["lightpath_capacity"],
        num_slots=net_cfg["num_slots"],
        max_steps=200,
        seed=42
    )
    
    # Initialize state
    env.reset(seed=42)
    
    traffic_on_ip_link = defaultdict(float)
    for (d_id, u, v), val in env.state.x.items():
        if val == 1 and d_id in demand_by_id:
            traffic_on_ip_link[(u, v)] += demand_by_id[d_id].bandwidth
            
    print("\n--- PHÂN TÍCH SLACK TRONG INITIAL STATE ---")
    
    # Find a good hop to test (e.g. hop with small slack, so removing a demand might push it to >= 80)
    target_hop = None
    target_demand_idx = -1
    target_demand = None
    
    for ip_link, load in traffic_on_ip_link.items():
        installed = env.cost_calc._installed_capacity_on_ip_link(env.state, ip_link)
        slack = installed - load
        print(f"Hop {str(ip_link):>8} | Load = {load:5.1f} | Installed = {installed:5.1f} | Slack = {slack:5.1f}")

    print("-" * 65)
    print(f"Init Cost hiện tại: {env.best_cost}")
    print("-" * 65)
    
    # Cố tình nhắm vào hop (4, 3) vì nó có Load = 165, Slack = 75 (chỉ thiếu 5 là đủ xóa 1 LP)
    target_hop = (4, 3)
    target_demand_idx = -1
    target_demand = None
    
    for i, d in enumerate(demands):
        edges = env.state.get_demand_edges(d.id)
        if target_hop in edges:
            try:
                ip_paths = list(nx.shortest_simple_paths(env.ip_graph, d.s, d.t))
                if len(ip_paths) >= 2:
                    target_demand_idx = i
                    target_demand = d
                    break
            except nx.NetworkXNoPath:
                pass
                
    if target_hop is None:
        print("[!] Không tìm thấy demand nào có thể reroute!")
        return
        
    print(f"\n[+] Thử nghiệm REROUTE_IP thủ công:")
    print(f"Chọn Demand idx={target_demand_idx}, id={target_demand.id}, bandwidth={target_demand.bandwidth}")
    print(f"Demand này đang đi qua hop {target_hop} có slack = {traffic_on_ip_link[target_hop]}")
    print(f"Route cũ của demand: {env.state.get_demand_edges(target_demand.id)}")
    
    action_reroute = config.OFFSET_REROUTE_IP + target_demand_idx
    obs, r, term, trunc, info = env.step(action_reroute)
    
    print(f"-> Sau reroute, cost: {info['cost']} | feasible: {info['feasible']} | action: {info['action_name']}")
    
    if info['feasible']:
        print(f"-> Route mới của demand: {env.state.get_demand_edges(target_demand.id)}")
        
        # Check load on target_hop again
        traffic_on_ip_link_new = defaultdict(float)
        for (d_id, u, v), val in env.state.x.items():
            if val == 1 and d_id in demand_by_id:
                traffic_on_ip_link_new[(u, v)] += demand_by_id[d_id].bandwidth
                
        new_load = traffic_on_ip_link_new[target_hop]
        new_installed = env.cost_calc._installed_capacity_on_ip_link(env.state, target_hop)
        new_slack = new_installed - new_load
        
        print(f"-> Hop {target_hop} Load mới = {new_load}, Installed = {new_installed}, Slack mới = {new_slack}")
        
        if new_slack >= 80.0:
            print("[+] TẠO THÀNH CÔNG ĐỦ SLACK ĐỂ XÓA LP!")
            # Try to remove an LP on this hop
            active_lp_ids = sorted(env.state.lightpath_info.keys())
            target_lp_logical_idx = -1
            for logical_idx, lp_id in enumerate(active_lp_ids):
                lp = env.state.lightpath_info[lp_id]
                if lp.ip_link == target_hop:
                    target_lp_logical_idx = logical_idx
                    break
                    
            if target_lp_logical_idx != -1:
                print(f"-> Xóa thử LP ở logical_idx {target_lp_logical_idx} (thuộc hop {target_hop})")
                action_remove = config.OFFSET_REMOVE_LP + target_lp_logical_idx
                obs2, r2, term2, trunc2, info2 = env.step(action_remove)
                print(f"-> Sau remove, cost: {info2['cost']} | feasible: {info2['feasible']}")
    else:
        print("[!] Reroute IP gây ra Infeasible (có thể do đường mới không đủ Capacity, và Agent chưa cắm ADD_LP dọn đường trước)")

if __name__ == "__main__":
    main()
