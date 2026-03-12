# a multi-agent collaboration system based on an OpenClaw design of the 'separation of powers' governance structure in the United States

> Base openclaw on  A multi-agent system inspired by the U.S. separation of powers, integrating LLMs and mapping constitutional checks and balances into an agent collaboration architecture.

## Core Idea

This project maps the **U.S. constitutional principle of separation of powers** into a multi-agent system design:

| Constitutional Branch | System Mapping | Agent Roles |
|---------|---------|-----------|
| **Executive** | Task execution and command | President + Workers (Cabinet) |
| **Legislative** | Policy making and approval | Senate + House |
| **Judicial** | Compliance review and judgment | Supreme Court |

### Checks and Balances

| Relationship | Real-World Institution | System Implementation |
|---------|---------|---------|
| Legislative -> Executive | Congress passes laws, President signs or vetoes | Bills are sent to the President after passing both chambers |
| Executive -> Legislative | Presidential veto | The President can veto bills |
| Legislative -> Executive | Two-thirds override of veto | Congress can override a veto with a supermajority |
| Judicial -> Legislative / Executive | Judicial review | The Supreme Court reviews bills and executive orders |
| Legislative -> Executive | Impeachment power | The House initiates impeachment and the Senate holds trial |
| Executive -> Judicial | Judicial appointments | The President appoints and the Senate confirms |
| Legislative -> Budget | Power of the purse | The House initiates resource allocation bills |

## Architecture

```
                    WE THE PEOPLE (User / Frontend)
                        HTTP API -> Gateway
┌──────────────────────────────────────────────────────────────┐
│                  CONSTITUTIONAL FRAMEWORK                   │
│   EventBus | Registry | Router | LLMClient | Legislation   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ LEGISLATIVE  │  │  EXECUTIVE   │  │    JUDICIAL      │   │
│  │              │  │              │  │                  │   │
│  │ Senate       │  │ President    │  │ Supreme Court    │   │
│  │ - Bill review│  │ - Command    │  │ - Review         │   │
│  │ - Confirmation│ │ - Orders     │  │ - Judgment       │   │
│  │ - Impeachment│  │ - Sign/Veto  │  │ - Precedents     │   │
│  │              │  │      ↓       │  │ - Monitoring     │   │
│  │ House        │  │ Workers      │  │                  │   │
│  │ - Proposals  │  │ (Cabinet)    │  │                  │   │
│  │ - Impeachment│  │ State Dept   │  │                  │   │
│  │ - Budgeting  │  │ Defense      │  │                  │   │
│  │              │  │ Treasury     │  │                  │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
├──────────────────────────────────────────────────────────────┤
│ Self-Organization Engine: Emergence | Feedback | Adaptation │
│                           | Stigmergy                        │
└──────────────────────────────────────────────────────────────┘
```

## Legislative Process

```
1. Bill proposed
   ↓  Initiated by the House or proposed by the President
2. House vote
   ↓  Passed by simple majority
3. Senate vote
   ↓  Passed by simple majority (filibuster may apply)
4. Presidential signature
   ├── Sign -> Bill becomes law
   └── Veto
       ↓
5. Congressional override
   ├── Two-thirds majority -> Bill becomes law
   └── Fails to reach two-thirds -> Bill is blocked

At any time: Supreme Court judicial review
   -> Unconstitutional -> Bill becomes invalid
```

## LLM Configuration

The system uses an OpenAI-compatible API. Default configuration:

```python
LLM_CONFIG = {
    'api_key': 'your-api-key',
    'base_url': '',
    'model': '',
    'max_tokens': 12000,
}
```

You can override it with environment variables:

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4"
export MAX_TOKEN=8000
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the system
python main.py
```

After startup, the system automatically:
- launches the HTTP API service (default: `http://0.0.0.0:18790`)
- creates a three-branch government:
  - **Executive**: 1 President + 3 Workers (State / Defense / Treasury)
  - **Legislative**: 1 Senate + 1 House
  - **Judicial**: 1 Supreme Court
- runs the self-organization engine (emergence, feedback, stigmergy, adaptation)

## API Examples

### Chat (Most Common)

```bash
curl -X POST http://localhost:18790/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "我是特朗普，针对不同国家增收关税进行法案和计划，法院立法，众议院提案，参议院投票，最高法院审判，政府执行"}'
```

### Submit a Task

```bash
# Code generation
curl -X POST http://localhost:18790/api/task \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "codegen",
    "required_skill": "codegen",
    "data": {"requirement": "Implement an async HTTP client"}
  }'
```

### Query System Status

```bash
# System status (including three-branch status and bill state)
curl http://localhost:18790/api/status

# Agent list grouped by branch
curl http://localhost:18790/api/agents

# Health check
curl http://localhost:18790/api/health
```

## Project Structure

```
agent_system_USA/
├── config/
│   └── settings.py              # Global configuration, including LLM settings
├── core/
│   ├── agent.py                 # Base Agent class
│   ├── llm_client.py            # OpenAI-compatible LLM client
│   ├── message.py               # Message protocol, including branch-related message types
│   ├── event_bus.py             # Event bus
│   ├── registry.py              # Agent registry
│   └── environment.py           # Shared environment / stigmergy carrier
├── checks_balances/
│   ├── legislation.py           # Bill lifecycle management
│   └── judicial_review.py       # Judicial review system
├── self_org/
│   ├── emergence.py             # Emergence engine
│   ├── feedback.py              # Feedback loop
│   ├── adaptation.py            # Adaptive strategies
│   └── stigmergy.py             # Stigmergy management
├── gateway/
│   ├── gateway.py               # Gateway constitutional framework
│   ├── router.py                # Adaptive message router
│   └── http_api.py              # HTTP API service
├── agents/
│   ├── president.py             # President, head of the executive branch
│   ├── senate.py                # Senate, upper chamber of the legislature
│   ├── house.py                 # House, lower chamber of the legislature
│   ├── supreme_court.py         # Supreme Court, judicial branch
│   └── worker.py                # Worker, cabinet-level executor
├── skills/
│   ├── llm_skills.py            # LLM skill set
│   ├── search_skill.py          # Search skills
│   ├── analyze_skill.py         # Analysis skills
│   └── transform_skill.py       # Transformation skills
├── utils/
├── examples/
│   └── demo.py                  # Demo script
├── main.py                      # Entry point
└── requirements.txt
```

## Observable System Behaviors

After launching the system, you can observe the following institutional behaviors:

1. **Executive execution chain**: external task -> President -> cabinet department execution -> result returned
2. **Legislative flow**: House proposal -> House vote -> Senate vote -> presidential signature
3. **Presidential veto**: the President vetoes a bill, and Congress may override it with a two-thirds majority
4. **Judicial review**: the Supreme Court reviews the constitutional validity of bills and executive orders
5. **Emergency legislation**: when the system is overloaded, the House may automatically propose expansion bills
6. **Institutional protection**: constitutionally protected Agents (President, Senate, House, Supreme Court) cannot be deleted
7. **Self-organization**: stigmergy-based routing, load balancing, and automatic scaling
<img width="1908" height="1014" alt="3158964a-a7b5-4eb7-9efa-9ae44a663bee" src="https://github.com/user-attachments/assets/fa60c2eb-7c2c-4c7c-9ae1-463c81630223" />

## License

MIT License
