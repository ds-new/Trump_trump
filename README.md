# USA Three-Branch Agent System

> 基于美国三权分立（Separation of Powers）制度设计的智能多智能体系统，集成 LLM 大模型，将宪法制衡机制映射到 Agent 协作架构中。

## 核心理念

本系统将 **美国宪法** 的三权分立制度映射到多智能体系统设计中：

| 宪法制度 | 系统映射 | Agent 角色 |
|---------|---------|-----------|
| **行政权 (Executive)** | 任务执行与指挥 | President + Workers (内阁) |
| **立法权 (Legislative)** | 政策制定与审批 | Senate (参议院) + House (众议院) |
| **司法权 (Judicial)** | 合规审查与裁决 | Supreme Court (最高法院) |

### 制衡机制 (Checks & Balances)

| 制衡关系 | 现实制度 | 系统实现 |
|---------|---------|---------|
| 立法 → 行政 | 国会立法，总统签署/否决 | 法案经两院投票后送总统签署 |
| 行政 → 立法 | 总统否决权 | President 可否决法案 |
| 立法 → 行政 | 2/3 多数推翻否决 | Congress 超级多数推翻 VETO |
| 司法 → 立法/行政 | 违宪审查 | Supreme Court 审查法案和行政令 |
| 立法 → 行政 | 弹劾权 | House 发起弹劾，Senate 审判 |
| 行政 → 司法 | 法官任命 | President 任命，Senate 确认 |
| 立法 → 预算 | 拨款权 (Power of the Purse) | House 发起资源分配法案 |

## 架构

```
                     WE THE PEOPLE (用户/前端)
                      HTTP API → Gateway
┌──────────────────────────────────────────────────────────────┐
│                    CONSTITUTION (宪法框架)                     │
│  EventBus │ Registry │ Router │ LLMClient │ Legislation      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  LEGISLATIVE  │  │  EXECUTIVE   │  │    JUDICIAL      │   │
│  │  立法权       │  │  行政权       │  │    司法权         │   │
│  │              │  │              │  │                  │   │
│  │  Senate      │  │  President   │  │  Supreme Court   │   │
│  │  参议院       │  │  总统         │  │  最高法院         │   │
│  │  - 法案审议   │  │  - 任务指挥   │  │  - 违宪审查      │   │
│  │  - 任命确认   │  │  - 行政令     │  │  - 司法裁决      │   │
│  │  - 弹劾审判   │  │  - 签署/否决  │  │  - 判例体系      │   │
│  │              │  │      ↓       │  │  - 系统监控      │   │
│  │  House       │  │  Workers     │  │                  │   │
│  │  众议院       │  │  (内阁部门)   │  │                  │   │
│  │  - 发起法案   │  │  State Dept  │  │                  │   │
│  │  - 发起弹劾   │  │  Defense     │  │                  │   │
│  │  - 预算控制   │  │  Treasury    │  │                  │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
├──────────────────────────────────────────────────────────────┤
│  自组织引擎: Emergence │ Feedback │ Adaptation │ Stigmergy    │
└──────────────────────────────────────────────────────────────┘
```

## 法案生命周期 (Legislative Process)

```
1. 提案 (Bill Proposed)
   ↓  众议院发起 或 总统提议
2. 众议院投票 (House Vote)
   ↓  简单多数通过
3. 参议院投票 (Senate Vote)
   ↓  简单多数通过（可 Filibuster）
4. 总统签署 (Presidential Signature)
   ├── 签署 → 法案生效 (Enacted)
   └── 否决 (Veto)
       ↓
5. 国会推翻否决 (Veto Override)
   ├── 2/3 多数 → 法案生效
   └── 未达 2/3 → 法案搁置
       
随时: 最高法院违宪审查 (Judicial Review)
   → 违宪 → 法案无效 (Unconstitutional)
```

## 大模型配置

系统使用 OpenAI 兼容 API，默认配置：

```python
LLM_CONFIG = {
    'api_key': 'your-api-key',
    'base_url': '',
    'model': '',
    'max_tokens': 12000,
}
```

通过环境变量覆盖：

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4"
export MAX_TOKEN=8000
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动系统
python main.py
```

启动后系统自动：
- 启动 HTTP API 服务（默认 `http://0.0.0.0:18790`）
- 建立三权分立政府：
  - **行政**: 1 President + 3 Workers（国务院/国防部/财政部）
  - **立法**: 1 Senate + 1 House
  - **司法**: 1 Supreme Court
- 运行自组织引擎（涌现 / 反馈 / 信息素 / 自适应）

## 前端 API 接口

### 对话（最常用）

```bash
curl -X POST http://localhost:18790/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我写一个Python快速排序算法"}'
```

### 提交任务

```bash
# 代码生成
curl -X POST http://localhost:18790/api/task \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "codegen",
    "required_skill": "codegen",
    "data": {"requirement": "实现一个异步HTTP客户端"}
  }'
```

### 查询状态

```bash
# 系统状态（含三权分立信息、法案状态）
curl http://localhost:18790/api/status

# Agent 列表（按分支分组）
curl http://localhost:18790/api/agents

# 健康检查
curl http://localhost:18790/api/health
```

## 目录结构

```
agent_system_USA/
├── config/
│   └── settings.py              # 全局配置（含 LLM 配置）
├── core/
│   ├── agent.py                 # Agent 基类
│   ├── llm_client.py            # LLM 客户端（OpenAI 兼容）
│   ├── message.py               # 消息协议（含三权分立消息类型）
│   ├── event_bus.py             # 事件总线
│   ├── registry.py              # Agent 注册中心
│   └── environment.py           # 共享环境（信息素载体）
├── checks_balances/             # 🆕 制衡机制
│   ├── legislation.py           # 法案生命周期管理
│   └── judicial_review.py       # 司法审查系统
├── self_org/
│   ├── emergence.py             # 涌现引擎
│   ├── feedback.py              # 反馈循环
│   ├── adaptation.py            # 自适应策略
│   └── stigmergy.py             # 信息素管理
├── gateway/
│   ├── gateway.py               # Gateway 宪法框架
│   ├── router.py                # 自适应消息路由器
│   └── http_api.py              # HTTP API 服务
├── agents/                      # 🆕 三权分立 Agent
│   ├── president.py             # 总统（行政权首脑）
│   ├── senate.py                # 参议院（立法权上院）
│   ├── house.py                 # 众议院（立法权下院）
│   ├── supreme_court.py         # 最高法院（司法权）
│   └── worker.py                # Worker（内阁执行者）
├── skills/
│   ├── llm_skills.py            # LLM 技能集
│   ├── search_skill.py          # 搜索技能
│   ├── analyze_skill.py         # 分析技能
│   └── transform_skill.py       # 转换技能
├── utils/
├── examples/
│   └── demo.py                  # 演示脚本
├── main.py                      # 主入口
└── requirements.txt
```

## 三权分立行为观测

运行系统后，可以观察到以下制度性行为：

1. **行政执行链**: 外部任务 → 总统 → 内阁部门执行 → 结果回传
2. **立法流程**: 众议院提案 → 众议院投票 → 参议院投票 → 总统签署
3. **总统否决**: 总统否决法案 → 国会可 2/3 多数推翻
4. **司法审查**: 最高法院审查法案和行政令的"合宪性"
5. **紧急立法**: 系统过载时众议院自动提出扩容法案
6. **制衡保护**: 宪法保护的 Agent（总统/参议院/众议院/最高法院）不可被删除
7. **自组织涌现**: 信息素路由、负载自平衡、自动扩缩容
<img width="1908" height="1014" alt="3158964a-a7b5-4eb7-9efa-9ae44a663bee" src="https://github.com/user-attachments/assets/37a70771-5669-46d3-af5a-fc58bbe47d25" />

## 许可

MIT License
