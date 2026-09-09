# Nexus-Lark-Mind 架构图

```mermaid
flowchart TB
    subgraph WebFrontend["Web 前端 (Vue + Vite)"]
        WebApp["App.vue"]
        Views["views/"]
        Components["components/"]
        Composables["composables/"]
    end

    subgraph Adapters["Adapters (端口 8000)"]
        AdapterApp["app.py"]
        Feishu["feishu/"]
        Web["web/"]
        Channels["channels/"]
    end

    subgraph Orchestrator["Orchestrator (端口 8002)"]
        OrchApp["app.py"]
        TaskDispatcher["task_dispatcher.py"]
        QueueService["queue_service.py"]
    end

    subgraph CoreKernel["Core Kernel (端口 8001)"]
        KernelApp["app.py"]
        AgentRunner["agent_runner.py"]
        RpcServer["rpc_server.py"]
    end

    subgraph Infrastructure["Infrastructure"]
        Redis["Redis (6379)"]
        MemoryBroker["memory_broker.py"]
        Storage["storage/"]
    end

    %% Frontend -> Adapters
    WebApp --> AdapterApp
    WebApp --> Views
    WebApp --> Components
    WebApp --> Composables

    %% Adapters -> Orchestrator
    AdapterApp --> OrchApp
    AdapterApp --> Feishu
    AdapterApp --> Web
    AdapterApp --> Channels

    %% Orchestrator -> Core Kernel
    OrchApp --> KernelApp
    TaskDispatcher --> AgentRunner
    QueueService --> RpcServer

    %% Infrastructure
    Redis --> MemoryBroker
    MemoryBroker --> Storage

    %% Dependencies Flow
    AdapterApp -.->|"HTTP RPC"| CoreKernel
    OrchApp -.->|"HTTP RPC"| CoreKernel

    %% Event Bus
    OrchApp -.->|"Redis Event Bus"| CoreKernel
```

## 架构概览

| 层级 | 服务 | 端口 | 职责 |
|------|------|------|------|
| **Adapters** | 飞书/Web 入口 | 8000 | 飞书 webhook、Web SSE 对话页 |
| **Orchestrator** | 任务编排 | 8002 | 队列、会话、事件转发 |
| **Core Kernel** | 核心引擎 | 8001 | 模型网关、插件运行时、SQLite |
| **Infrastructure** | 基础设施 | - | Redis、内存代理、存储 |

## 关键设计

- **单向依赖**：Adapters → Orchestrator → Kernel → Infrastructure
- **唯一数据源**：只有 Core Kernel 可读写 SQLite，其他通过 HTTP RPC
- **事件总线**：Redis 作为全局事件总线连接各服务
- **插件系统**：支持 CLI、MCP、RPC 插件，自动注册
