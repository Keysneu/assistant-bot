# gemma4_vLLM.md

更新时间：2026-04-05  
目标：在 `RTX 4090 24GB * 1` 服务器上，为当前 AssistantBot 项目接入 `Gemma 4 E4B-it` + vLLM（远程推理，本地后端调用）。

---

## 1. 结论与模型选择

### 推荐模型
- 生产首选：`google/gemma-4-E4B-it`

### 为什么是 E4B（结合本项目 + 4090 24GB）
- 你的项目是 RAG + SSE 流式对话，稳定性优先于极限模型尺寸。
- Gemma 4 官方内存参考中，E4B 显存需求远低于 31B，24GB 单卡可稳定运行并保留 KV cache 空间。
- `31B-it` 在 24GB 单卡下长期服务风险高（显存抖动、并发受限、OOM 风险）。

---

## 2. 当前项目现状（与改造相关）

当前仓库已具备 vLLM 通路，不需要重写架构：
- 后端 provider 已支持 `vllm`  
  [backend/app/core/config.py](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/backend/app/core/config.py)
- LLM 调用已走 OpenAI-compatible API（含流式）  
  [backend/app/services/llm_service.py](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/backend/app/services/llm_service.py)
- 已有 vLLM 启动脚本与部署文档（当前默认 Qwen，需要切到 Gemma4）  
  [deploy/vllm/start_vllm.sh](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/deploy/vllm/start_vllm.sh)  
  [deploy/vllm/.env.example](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/deploy/vllm/.env.example)  
  [deploy/vllm/README.md](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/deploy/vllm/README.md)

---

## 3. 服务器端需要修改什么（4090 + vLLM）

## 3.1 必改项（不改代码逻辑，只改部署配置）

1. 模型切换
- `MODEL_NAME` 从 `Qwen/Qwen2.5-7B-Instruct` 改为 `google/gemma-4-E4B-it`

2. 资源参数（首发建议）
- `GPU_MEMORY_UTILIZATION=0.88`（可在 0.85~0.92 微调）
- `MAX_MODEL_LEN=8192`（先稳态，后续再评估 16384+）
- 建议增加：
  - `--max-num-seqs 16`（控制并发占用）
  - `--async-scheduling`（提高吞吐）

3. 模型名映射建议
- 建议加 `--served-model-name gemma4-e4b-it`
- 好处：后端配置不依赖 HF 原始 repo 名，后续换版本更稳

4. 网络与鉴权
- API Key 必须开启（不要裸奔）
- 仅开放给后端来源 IP / 内网 / 隧道入口

## 3.2 强建议项（生产稳定性）

1. CUDA 13.0 环境建议优先 Docker 路径（减少轮子兼容问题）
- 若走容器，优先官方 Gemma4 对应镜像标签（含 CUDA13 变体）

2. 磁盘规划
- 系统盘仅 30GB 时，建议将 HF 缓存目录迁移到大盘
- 典型做法：设置 `HF_HOME` 到数据盘路径，避免模型与缓存挤爆系统盘

3. 服务托管
- 使用 systemd 管理 vLLM 进程（自启动、崩溃拉起、日志归档）

---

## 4. 本地（Mac）需要修改什么

## 4.1 必改项（运行配置）

修改本地后端 `.env`（文件不入库）：
- `LLM_PROVIDER=vllm`
- `VLLM_BASE_URL=http://<SERVER_IP_OR_TUNNEL>:8100/v1`
- `VLLM_API_KEY=<你的服务端key>`
- `VLLM_MODEL=gemma4-e4b-it`（若服务端配置了 `--served-model-name`）  
  否则用 `google/gemma-4-E4B-it`

说明：
- 前端基本不需要改；前端仍只连本地 FastAPI。
- SSE 流式链路无需改。

## 4.2 建议项（当前项目中的可见优化点，暂不改代码）

1. `/api/chat/` 返回 metadata 里模型名目前写死为 qwen，建议后续改为动态  
- 位置：  
  [backend/app/api/chat.py](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/backend/app/api/chat.py)

2. 健康检查建议增加 vLLM 主动探活（当前 `vllm` 分支下逻辑偏“假健康”）  
- 位置：  
  [backend/app/api/health.py](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/backend/app/api/health.py)  
  [backend/app/services/llm_service.py](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/backend/app/services/llm_service.py)

---

## 5. 仓库内需要更新的文档/脚本清单（本轮先记录，不实施）

## 5.1 需更新文件
- [deploy/vllm/start_vllm.sh](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/deploy/vllm/start_vllm.sh)
- [deploy/vllm/.env.example](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/deploy/vllm/.env.example)
- [deploy/vllm/README.md](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/deploy/vllm/README.md)
- [README.md](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/README.md)
- [todo.md](/Users/moem/Desktop/Deep%20Learning/LLM/基于大模型对话机器人创建项目/对话机器人助手/assistant-bot/todo.md)

## 5.2 文档中应体现的关键信息
- 默认远程模型切换为 `Gemma 4 E4B-it`
- 4090 推荐参数（显存利用率/上下文长度/并发）
- CUDA13 优先部署路径说明（Docker 或已验证 wheel）
- 回滚策略（模型回切 Qwen 或降级 E2B）

---

## 6. 推荐首发参数（文本RAG优先）

- `MODEL_NAME=google/gemma-4-E4B-it`
- `PORT=8100`
- `HOST=0.0.0.0`
- `API_KEY=<non-empty>`
- `GPU_MEMORY_UTILIZATION=0.88`
- `MAX_MODEL_LEN=8192`
- 增加参数：
  - `--max-num-seqs 16`
  - `--async-scheduling`
  - `--served-model-name gemma4-e4b-it`
  - 可选：`--generation-config vllm`（避免模型仓库默认 generation_config 覆盖你后端采样参数）

说明：
- 当前项目主链路是文本 RAG。Gemma4 多模态/工具调用参数（reasoning parser/tool parser）可后续再启用，不建议首发一起上。

---

## 7. 验收与回归检查（上线前）

1. 服务器端
- `/v1/models` 能返回 `gemma4-e4b-it`（或原模型名）
- 连续压测 10~20 分钟无 OOM / 重启

2. 本地后端
- `/api/health/` 正常
- `/api/chat/stream` 稳定返回 token
- RAG 检索 + 回答链路可用

3. 前端
- 多轮会话、流式显示、错误提示正常

---

## 8. 风险与回滚

## 8.1 主要风险
- 30GB 系统盘被模型缓存挤满
- 并发拉高后 KV cache 抢占导致时延抖动
- 服务端 model_name 与本地 `VLLM_MODEL` 不一致导致 404

## 8.2 回滚策略
1. 仅回滚模型名到之前 Qwen（不改后端代码）
2. 保持 vLLM 架构不变，先恢复可用性
3. 再逐步重新压测 Gemma4 参数

---

## 9. 本轮范围说明

本轮仅输出改造分析与文档清单：
- 不改代码
- 不改脚本
- 不改环境

下一轮如需实施，可按本文件逐项落地。
