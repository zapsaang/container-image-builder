# AGENTS.md - Container Image Builder

本文件为 `container-image-builder` 仓库的智能体与开发者指引。在修改、扩展或测试本仓库时，必须严格遵守以下规范与要求。

## 1. 仓库定位与核心架构

`container-image-builder` 是一个基于 GitHub Actions 的轻量级容器镜像自动化构建与分发系统。其目标是将多个上游 GitHub 项目构建为独立的 GHCR (GitHub Container Registry) 镜像并持续保持更新。

### 核心设计原则
- **零外部依赖**：`scripts/` 内所有脚本仅使用 Python 标准库（Python 3.10+），可在 GitHub-hosted runner 上开箱即用，禁止引入 `pip` 第三方依赖。
- **声明式配置**：每个镜像的构建规则通过 `images/<name>.json` 声明。
- **智能增量构建（Smart Skip / Retag）**：
  - 检查目标镜像及其平台的 OCI Manifest 与 Digest。
  - 若已存在完整多架构镜像且 `latest` 指向一致，则 `skip`；
  - 若已有镜像且架构完整但 `latest` 指针缺失或漂移，则仅 `retag`（通过 `docker buildx imagetools create` 更新 tag，无需重新编译）；
  - 仅在镜像不存在、架构不完整或设置 `force=true` 时执行全新 `build`。
- **安全与边界防护**：严格拦截路径遍历（阻止 `..` 与绝对路径），严格限制 `:latest` 仅允许绑定到 `latest-release`（防止历史 pinned tag 导致版本回退）。

---

## 2. 目录结构与职责划分

```text
.
├── images/                  # 镜像配置文件目录（每个工具一个 JSON）
│   ├── ssh-mcp.json        # 生产启用的镜像配置示例
│   └── second-image.json   # 模板与禁用示例
├── dockerfiles/             # （可选）当 dockerfile_source="local" 时自定义 Dockerfile 存放目录
│   └── <name>/Dockerfile   # 如 dockerfiles/my-tool/Dockerfile
├── scripts/                 # 核心流水线辅助脚本（纯 Python 标准库）
│   ├── config.py           # 配置读取、Schema 校验与安全过滤
│   ├── plan.py             # 读取 images/*.json 生成 GitHub Actions Matrix
│   ├── resolve.py          # 解析上游最新 Release 或固定 Tag，生成 GHCR 目标 Tags
│   └── registry.py         # 探测 GHCR 镜像状态并决策行为 (build / retag / skip)
├── tests/                   # 单元测试（基于 unittest）
│   ├── test_config.py      # 配置校验、路径安全与计划过滤测试
│   └── test_registry.py    # Registry 决策与探测逻辑测试
└── README.md                # 用户与操作使用说明
```

---

## 3. 开发与验证工作流

在声明任务完成或提交代码前，必须在本地完整运行以下验证命令并确保全绿：

```bash
# 1. 运行所有单元测试
python3 -m unittest discover -s tests -v

# 2. 运行构建矩阵规划测试
python3 scripts/plan.py

# 3. 指定单一镜像规划测试
IMAGE_FILTER=ssh-mcp python3 scripts/plan.py
```

### 测试与修改纪律
- **先红后绿（TDD）**：增加新的校验规则或修复缺陷时，先编写/补充测试使门禁变红，再编写实现使其变绿。负例测试作为回归测试永久保留。
- **单源标准**：不要修改已有测试的断言来迎合有缺陷的实现，改动必须向下兼容已定义的配置规范。
- **小步修改**：改动尽量小、与既有结构一致；不做未被要求的重构或顺手清理。

---

## 4. 镜像配置规范 (`images/*.json`)

添加或编辑 `images/<name>.json` 时必须遵守：

1. **文件名与 `name` 严格一致**：文件名必须为 `<name>.json`，且内容中的 `"name"` 字段必须严格等于文件名去掉 `.json` 的 stem。
2. **命名字符集规范**：
   - 镜像名称需匹配正则：`^[a-z0-9]+(?:[._-][a-z0-9]+)*$`（小写字母、数字，允许点、下划线、短横线作为分隔符）。
   - 上游仓库 `repository` 必须为 `OWNER/REPO` 格式（匹配 `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`）。
3. **版本策略 (`version`)**：
   - `{"strategy": "latest-release"}`：调用 GitHub API 追踪最新非 draft、非 prerelease 版本。
   - `{"strategy": "tag", "tag": "vX.Y.Z"}`：固定特定 tag 构建（tag 需符合 `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`）。
4. **`publish_latest` 约束**：
   - 只有 `strategy == "latest-release"` 时才允许 `publish_latest: true`。
   - 固定 tag 策略下必须为 `publish_latest: false`，杜绝覆盖 `:latest`。
5. **构建参数 (`build`)**：
   - `context`: 必须是上游检出根目录内的相对规范路径，不得包含 `..`、空片段或反斜杠。
   - `dockerfile`: 同上，相对路径。
   - `dockerfile_source`: 可选 `"upstream"` (默认) 或 `"local"`。若为 `"local"`，必须存在 `dockerfiles/<name>/<dockerfile>` 文件。
   - `platforms`: 支持列表 `["linux/amd64", "linux/arm64"]` 的非空子集，不可包含重复项。

---

## 5. 核心脚本实现规范与安全红线

- **严禁引入第三方依赖**：`scripts/` 下的所有代码一律不得 `import` 任何外部 pip 包。
- **错误处理保真**：
  - 在 `scripts/registry.py` 中探测 GHCR 状态时，除了明确匹配 404 / manifest unknown 为镜像不存在外，其他任何网络、权限或未知异常必须 raise 显式抛错，严禁将其降级或视作镜像不存在。
- **环境变量交互**：
  - 各脚本专为 GitHub Actions 设计，通过环境变量（如 `GITHUB_OUTPUT`、`REGISTRY_IMAGE`、`IMAGE_VERSION` 等）输入输出。本地脱机运行时需有合理 fallback 或支持独立测试。
- **安全与机密隔离**：
  - 上游代码和 Dockerfile 视作不可信代码，绝不能在镜像构建环境暴露主机敏感凭据或 Personal Access Token。
  - GHCR 发布流程仅依靠 Actions 提供的临时 `GITHUB_TOKEN` (`packages: write`)。
