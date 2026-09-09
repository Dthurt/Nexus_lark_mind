# Remote SSH workspaces

Nexus Lark Mind can treat a **remote folder over SSH** as a coding-agent workspace (same tools as local).

## Flow

1. Empty chat → **工作目录 → 远程 SSH**
2. **本机 SSH 配置**：读取 `~/.ssh/config`（Windows: `%USERPROFILE%\.ssh\config`）中的 Host 别名，一键 **导入**
3. 或 **手动添加**：填 Host / Port / Username + 密码或私钥 → 保存（`data/ssh_hosts.json`）
4. **测试**连通性 → **浏览远程目录**（SFTP）→ **选用远程目录**
4. Agent 使用 `builtin.workspace`（`list_dir` / `read_file` / `write_file` / `edit_file` / `run_shell`），经 SSH/SFTP 在远程执行

## API

```bash
GET    /api/ssh/config/hosts          # list Host aliases from ~/.ssh/config
POST   /api/ssh/hosts/import          # { "alias": "my-server" }
GET    /api/ssh/hosts
POST   /api/ssh/hosts
DELETE /api/ssh/hosts/{id}
POST   /api/ssh/hosts/{id}/test
GET    /api/ssh/hosts/{id}/browse?path=~

POST   /api/workspaces   # { "kind":"ssh", "ssh_host_id":"...", "path":"/home/u/proj" }
```

Session fields: `workspace_kind=ssh`, `ssh_host_id`, `cwd=<remote path>`.

## Notes

- Depends on `asyncssh`（已写入 `requirements.txt`）
- MVP 使用 `known_hosts=None`（首次连接不校验 host key）；仅在可信网络使用
- 密钥可填 PEM 文本或本机密钥文件路径
- 从 `ssh_config` 导入的主机使用 `asyncssh` 读取本机 OpenSSH 配置（含 IdentityFile、ProxyJump 等，取决于 asyncssh 支持范围）
