# Pure PPO training

Thư mục này train và inference `MaskablePPO` trực tiếp trên môi trường
cross-layer. Policy chọn demand và candidate IP path; SA/LNS không được gọi để
train, làm teacher hay fallback khi inference. Môi trường chỉ repair capacity,
gán spectrum và loại lightpath dư để mọi state tuân theo hard constraints.

Chạy nhanh từ thư mục gốc:

```powershell
python -m training.train_ppo --timesteps 4096
python -m training.evaluate_and_plot
```

Train mạnh hơn với teacher MILP/CPLEX có bản quyền:

```powershell
python -m training.train_milp_teacher_ppo --timesteps 8192 --bc-epochs 25
python -m training.evaluate_and_plot --checkpoint training/artifacts_milp/ppo_milp_teacher.zip --fast-greedy --top-k 32 --fast-max-steps 24 --label "Fast MILP-Teacher PPO" --csv-name ppo_milp_fast_top32.csv --plot-name 01_fast_milp_teacher_ppo_top32.png
```

Fine-tune curriculum cho tải lớn:

```powershell
python -m training.fine_tune_large_loads --timesteps 4096
```

Vẽ thêm đường optimum CPLEX trên cùng đồ thị:

```powershell
python -m training.plot_milp_comparison
```

So sánh runtime của đủ năm phương pháp (PPO dùng một trajectory top-32):

```powershell
python -m training.plot_runtime_comparison
```

Artifact chính:

- `training/artifacts/ppo_short.zip`: checkpoint PPO.
- `training/artifacts/ppo_short.metadata.json`: cấu hình observation/action.
- `training/artifacts/training_curve.png`: learning curve.
- `training/results/ppo_inference.csv`: kết quả inference.
- `results/01_initial_vs_sa_vs_lns_vs_ppo.png`: plot so sánh bốn phương pháp.
