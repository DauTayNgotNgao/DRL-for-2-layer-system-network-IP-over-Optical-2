Cross-Layer Optimization Using Simulated Annealing
Đây là project mô phỏng bài toán tối ưu đa lớp giữa tầng IP và tầng quang. Hệ thống sinh topology mạng quang, topology mạng IP, ánh xạ node IP xuống node quang, sinh các traffic demand, khởi tạo trạng thái ban đầu và dùng thuật toán Simulated Annealing (SA) để tối ưu cấu hình mạng.
Mục tiêu chính của project là so sánh chi phí của cấu hình ban đầu với cấu hình sau tối ưu, từ đó đánh giá hiệu quả của thuật toán trong bài toán tối ưu đa lớp.
---
1. Ý tưởng bài toán
Trong mạng đa lớp, tầng IP chịu trách nhiệm định tuyến lưu lượng giữa các router logic, trong khi tầng quang cung cấp các lightpath vật lý để truyền tải lưu lượng đó. Một demand ở tầng IP có thể đi qua nhiều IP link, và mỗi IP link cần được hỗ trợ bởi một hoặc nhiều lightpath ở tầng quang.
Project này mô hình hóa các thành phần chính:
Optical network: mạng vật lý gồm các node quang và fiber link.
IP network: mạng logic gồm các router IP và IP link.
IP-to-optical mapping: ánh xạ mỗi node IP xuống một node quang.
Traffic demands: các yêu cầu truyền lưu lượng giữa các node IP.
Lightpaths: các kết nối quang hỗ trợ cho IP link.
Spectrum slots: tài nguyên phổ được cấp phát cho các lightpath.
Thuật toán SA được sử dụng để cải thiện cấu hình ban đầu thông qua các thao tác như đổi đường đi IP, thêm lightpath hoặc xóa lightpath.
---
2. Cấu trúc thư mục
```text
src_hung/
│
├── main.py
│
├── model/
│   ├── demand.py
│   ├── lightpath.py
│   ├── network.py
│   └── state.py
│
├── algorithms/
│   ├── routing.py
│   ├── spectrum.py
│   └── sa.py
│
├── objective/
│   └── cost_func.py
│
├── visualization/
│   └── plot_results.py
│
└── experiments/
    └── demand_sweep.py

results/
├── draw_my_results.py
├── demand_sweep_raw.csv
├── demand_sweep_summary.csv
├── 01_initial_vs_sa_total_cost.png
├── 02_initial_vs_sa_normalized_cost.png
├── 03_improvement_percent.png
└── 04_feasible_rate.png
```
3. Cài đặt môi trường
Yêu cầu Python từ phiên bản 3.10 trở lên.
Tạo môi trường ảo:
```bash
python -m venv .venv
```
Kích hoạt môi trường ảo trên Windows PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
```
Cài thư viện cần thiết:
```bash
pip install networkx matplotlib pandas pyyaml pytest
```
4. Cách chạy chương trình
Chạy lệnh:
```bash
python -m src_hung.experiments.demand_sweep --demand-points 2,4,6,8,10 --repetitions 1 
```
note: ``` "--demand-points {tập demands nhập từ bàn phím cách nhau}" ```