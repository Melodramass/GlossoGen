# textcraft 团队规模实验（N = 1, 3, 10）运行说明

分支 `textcraft-scale`（基于上游 GlossoGen main）。实验目录就是本目录。

## 实验设置

- 任务：16 个 12 列 × 6 层的 layered 任务（`tasks_w12_l6.json`，seed 1001–1016），每个任务 72 次 craft；每列有私有原料，供给精确；cross-edge density 0.3；每次 craft 耗时 30 虚拟秒。
- recipe 逐步解锁（`recipe_reveal=frontier`）：开局只给第一层，某个 recipe 的输入第一次全部出现在 depot 里时，对所有人解锁。
- 5 个 arm：`solo`、`n3_nocomm`、`n3_comm`、`n10_nocomm`、`n10_comm`，共 80 局。
- 所有 arm 都可以用 `read_notifications(wait_for="depot", items=[...])` 等待物品或新解锁的 recipe。
- 模型：Qwen3.5-27B，non-thinking；每次请求按 1 s + 输出 token / 50 计虚拟时间。
- oracle 加速上限：N=3 为 3.0x，N=10 为 9.0x。

## 新机器上的准备

```bash
git clone git@github.com:Melodramass/GlossoGen.git
cd GlossoGen && git checkout textcraft-scale
uv sync                                   # 生成 .venv，run_batch.py 用 .venv/bin/python
# vLLM（测试用的是 0.27.1）要在 PATH 上，或者设 CONDA_SH / CONDA_ENV 让 start_server.sh 去激活
export HF_HOME=/path/to/hf_cache          # 下面这份权重要已经下载好
huggingface-cli download Qwen/Qwen3.5-27B
```

`start_server.sh` 默认 `HF_HUB_OFFLINE=1`，并且会激活 Vista 上的 conda 环境。换机器时设
`CONDA_SH=`（留空，直接用 PATH 上的 vllm）和 `HF_HOME`。

## 运行

单机多卡（例如 2 张 GB200），每张卡一个 vLLM 副本：

```bash
cd experiments/textcraft_scale_20261019
SMOKE=1 bash run_local_gpus.sh            # 先跑 t00 的 5 个 arm，确认团队组能跑完
bash run_local_gpus.sh                    # 全量 80 局；已完成的会跳过，重跑即续跑
GPUS=0,1 JOBS_PER_GPU=4 bash run_local_gpus.sh
```

已经有 vLLM 在跑时，直接把地址交给 `run_batch.py`：

```bash
../../.venv/bin/python run_batch.py --nodes host1:8010 host2:8010 --jobs-per-node 4
```

Vista 上从 login 节点提交：`mkdir -p slurm && sbatch textcraft_scale_gh.sbatch`。

## 看进度和结果

```bash
python3 progress.py                       # 每局：完成的 craft 数、被拒的 act、请求数、最长输出、虚拟时间
../../.venv/bin/python summarize.py       # 每个 arm 和 solo 按任务配对：成功率、makespan、加速比、效率
```

每局的事件日志在 `jobs/<arm>_tNN/runs/textcraft_shared_workspace/*/textcraft_shared_workspace.jsonl`，
`result.json` 是该局的汇总。

## 已知情况（Vista 上 smoke 的结论）

- Qwen3.5-27B 调用无参数的 `observe` 时，常在 `<function=observe>` 后面输出成串的制表符。
  请求里带了 vLLM 的 `repetition_detection`，这种输出会在约 32 次重复后被截断，工具调用照常解析。
  这需要 vLLM 支持该参数（0.27 支持）。
- 每条回复最多一个工具调用，在 `</tool_call>` 处停止。
- `agent_max_tokens=16384`。后期会有少数 agent 长篇乱猜，直到这个上限（例如
  "I realize I'm just guessing"）。这会算进虚拟时间，也会拖慢墙钟。
- 同一个 recipe 可以重复做。重复的那次会偷走另一个下游需要的共享中间产物，可以用 uncraft 补救。
  smoke 里 27B 从没用过 uncraft，团队组曾卡在约 40/72，直到撞上墙钟上限 `WALL_SECONDS=5400`。
- `--override-generation-config` 里的 `presence_penalty` 在 vLLM 0.27 不生效，请求实际按 0 运行。
