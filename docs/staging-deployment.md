# 将构建产物自动部署到 staging

本节基于已经配置好的 CI、Artifact、GitHub staging Environment 和服务器部署账号。
文中的服务器地址统一使用 `服务器公网IP` 占位；真实值只填在 GitHub Environment 的 `DEPLOY_HOST` 中。

## 这次要实现的流程

```text
PR → 测试和构建（部署 Job 跳过）
合并到 main → 测试和构建 → 上传 Artifact
                         → 下载同一份 Artifact → SSH 部署 staging → HTTP 验证
```

部署不重新运行 npm build。不同 Job 通常使用独立 Runner；`needs` 负责等待，Artifact 负责传递文件。

## 1. 已准备的部署脚本

`ops/deploy-staging.py` 只操作服务器的 `/opt/cicd-web/environments/staging`。
它用 Python 标准库解压产物、核对提交 SHA、保留版本目录、切换 current 链接，随后检查 HTTP 服务。
检查失败时恢复原来的 current 和环境信息，并以非零状态退出，让 Actions 显示失败。

它不需要 sudo、Docker 权限或服务器上的 Node.js。原管理员脚本仍用于此前的手动部署流程。

`staging/current` 指向的旧版本目录可能位于原来的共享 releases 下，新脚本能够恢复这个链接。
新的 staging 版本放在 staging 自己的 releases 下。以后部署 production 时下载同一个 Artifact，
复制到 production 的版本目录；不要让 production 依赖 staging 账号可修改的目录。

## 2. 在 ci.yml 中追加部署 Job

先在现有 `test` Job 的 `npm test` 步骤后增加一个检查：

```yaml
      - name: Test staging deployment script
        run: python3 -m unittest discover -s ops/tests -v
```

`ops/tests/test_deploy_staging.py` 是本次新增的测试文件，用来测试 `ops/deploy-staging.py`，
不是 GitHub 自动生成的步骤，也不是此前的前端测试。
测试会创建临时目录和模拟版本文件，启动一个仅监听 127.0.0.1 随机可用端口的小型 HTTP 服务，
再调用部署脚本，检查正常发布和 HTTP 校验失败时恢复旧版本的行为；结束后关闭服务并清理临时目录。

这里的“本机”指执行测试进程的那台机器：在 Actions 的 test Job 中就是 Runner；
在 Mac 终端手动执行同一命令时就是 Mac。测试将临时目录和 HTTP 地址传入部署函数，
覆盖正式部署的默认路径与地址，所以这组测试不连接 EC2，也不更新实际 staging。
正式部署时脚本运行在 EC2 上，其默认 127.0.0.1:18082 才指 EC2 上真正的 staging 服务。
这些测试不覆盖 SSH、GitHub Secret 或真实 Nginx 配置；首次实际部署仍需验证。
ubuntu-latest 自带 Python 3，本步骤无需安装第三方 Python 依赖。

把下面整个代码块追加到 `.github/workflows/ci.yml`，`deploy_staging:` 与 `test:` 对齐，
都是 `jobs:` 下的键。它不是 `test.steps` 中的一个步骤。
现有上传 Artifact 的步骤保持原样。

```yaml
  deploy_staging:
    name: Deploy staging
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment: staging

    # 同一时间只运行一个 staging 部署，不中断正在切换版本的任务
    concurrency:
      group: deploy-staging
      cancel-in-progress: false

    env:
      DEPLOY_HOST: ${{ vars.DEPLOY_HOST }}
      DEPLOY_PORT: ${{ vars.DEPLOY_PORT }}
      DEPLOY_USER: ${{ vars.DEPLOY_USER }}

    steps:
      # 获取仓库中的部署脚本；前端文件来自下面下载的 Artifact
      - name: Checkout deployment script
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Download frontend artifact
        uses: actions/download-artifact@v7
        with:
          name: frontend-dist-${{ github.sha }}
          path: dist

      - name: Configure SSH
        env:
          DEPLOY_SSH_KEY: ${{ secrets.DEPLOY_SSH_KEY }}
          DEPLOY_KNOWN_HOSTS: ${{ vars.DEPLOY_KNOWN_HOSTS }}
        run: |
          : "${DEPLOY_HOST:?Missing DEPLOY_HOST}"
          : "${DEPLOY_PORT:?Missing DEPLOY_PORT}"
          : "${DEPLOY_USER:?Missing DEPLOY_USER}"
          : "${DEPLOY_SSH_KEY:?Missing DEPLOY_SSH_KEY}"
          : "${DEPLOY_KNOWN_HOSTS:?Missing DEPLOY_KNOWN_HOSTS}"

          # 新文件默认仅当前用户能访问
          umask 077
          mkdir -p "$RUNNER_TEMP/staging-ssh"
          printf '%s\n' "$DEPLOY_SSH_KEY" > "$RUNNER_TEMP/staging-ssh/key"
          printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$RUNNER_TEMP/staging-ssh/known_hosts"

          # staging 是这份 SSH 配置中的连接别名
          cat > "$RUNNER_TEMP/staging-ssh/config" <<EOF
          Host staging
            HostName $DEPLOY_HOST
            User $DEPLOY_USER
            Port $DEPLOY_PORT
            IdentityFile $RUNNER_TEMP/staging-ssh/key
            UserKnownHostsFile $RUNNER_TEMP/staging-ssh/known_hosts
            IdentitiesOnly yes
            BatchMode yes
            StrictHostKeyChecking yes
            ConnectTimeout 10
            ServerAliveInterval 30
            ServerAliveCountMax 3
          EOF

      - name: Upload and deploy staging
        run: |
          ssh_config="$RUNNER_TEMP/staging-ssh/config"
          upload_id="${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"

          # 把已经下载好的 dist 打包，便于一次传输
          tar -czf "$RUNNER_TEMP/frontend.tar.gz" -C dist .
          ssh -F "$ssh_config" staging "mkdir -p incoming/$upload_id"
          scp -F "$ssh_config" \
            "$RUNNER_TEMP/frontend.tar.gz" \
            ops/deploy-staging.py \
            "staging:incoming/$upload_id/"

          # SSH 会将远程脚本的退出状态传回来：验证失败，Job 就失败
          # trap 在远程命令结束时清理本次上传的临时文件
          ssh -F "$ssh_config" staging \
            "trap 'rm -rf -- incoming/$upload_id' EXIT; python3 incoming/$upload_id/deploy-staging.py incoming/$upload_id/frontend.tar.gz '$GITHUB_SHA'"

      - name: Clean up local SSH files
        if: always()
        run: |
          rm -rf -- "$RUNNER_TEMP/staging-ssh"
          rm -f -- "$RUNNER_TEMP/frontend.tar.gz"
```

关键字段：

| 配置 | 含义 |
|---|---|
| `needs: test` | 等待 test Job 成功后再执行，文件仍需要通过 Artifact 传递 |
| Job 上的 `if` | 只部署 main 的 push；PR 和手动触发都跳过，和上传步骤的条件一致 |
| `environment: staging` | 关联 GitHub Environment、应用部署规则，并使用对应变量和 Secret |
| `concurrency` | 避免同时切换 staging；不是保证每个排队提交都会部署的队列 |
| `download-artifact` | 默认下载当前这次 Workflow 运行的产物，名称与上传时一致；无需另配 GitHub Token |
| `persist-credentials: false` | checkout 后不保留用于访问仓库的 Git 认证信息 |
| `env` | 将 GitHub 的变量或 Secret 放入进程环境，再由 Shell 读取 |
| `RUNNER_TEMP` | GitHub Runner 的临时目录 |
| `GITHUB_RUN_ID` / `GITHUB_RUN_ATTEMPT` | 区分不同工作流运行和重跑，避免上传目录相互覆盖 |
| `GITHUB_SHA` | 这次运行的提交；脚本检查产物的 release.json 是否属于该提交 |
| `ssh -F` / `scp -F` | 使用指定 SSH 配置文件；staging 这个 SSH 别名和 GitHub Environment 名称是独立概念 |
| `if: always()` | 在前序失败等情况下也尝试清理；Runner 被强制终止时不能保证执行 |

私钥仅在配置 SSH 的步骤作为环境变量出现，随后保存在权限受限的临时文件中。
服务器主机密钥必须与已配置的 known_hosts 匹配，不关闭服务器身份检查。

## 3. 让页面版本变化

把根目录 VERSION 从 `1.0` 改为 `1.1`。这个文件才控制页面版本，package.json 的 version 不控制页面。

## 4. 提交 PR

确认当前分支为 `feat/deploy-staging`，查看改动后执行：

```bash
git diff
git add .github/workflows/ci.yml ops/deploy-staging.py ops/tests/test_deploy_staging.py docs/staging-deployment.md VERSION
git commit -m "ci: deploy main build to staging"
git push -u origin feat/deploy-staging
```

创建目标为 main 的 PR。此时 test 应成功，Deploy staging 应显示 Skipped。
测试通过并确认代码后，标记 Ready for review，再合并。

合并后的 main push 运行应依次完成 test 和 Deploy staging。
远程部署脚本成功时输出 `Deployed staging: ...`，包含版本和提交信息。

## 5. 验证实际页面

使用之前的管理员 SSH 隧道访问本机 http://127.0.0.1:18082 查看 staging。
如果隧道已经断开，在 Mac 另开终端，替换服务器地址后运行并保持终端打开：

```bash
ssh -i ~/Documents/wf-2.pem -o StrictHostKeyChecking=yes -N \
  -L 127.0.0.1:18082:127.0.0.1:18082 \
  -L 127.0.0.1:18083:127.0.0.1:18083 \
  ubuntu@服务器公网IP
```

staging 应显示 `1.1`，提交应对应这次 main 的合并提交；production 应继续显示此前的版本。
两个服务端口仍只监听服务器回环地址，不需要为网页开放新的公网端口。
部署账号的公钥设有 restrict，不允许端口转发，因此浏览器预览仍用原来的管理员隧道。

本地 SSH 连通并不保证 GitHub Runner 的来源 IP 也获准连接。
若 Actions 在连接服务器时超时，核查 EC2 安全组/网络访问规则；不要先把所有端口开放到公网。
若失败是 `Permission denied (publickey)`，核对 DEPLOY_USER、公钥授权与 Secret 是否对应。

## 当前范围

本节只完成 staging 自动部署，production 暂不自动发布。旧版本目录会保留用于回滚；
当前脚本不自动清理历史版本，学习过程中留意服务器磁盘剩余空间。
只有 PR 合并后的真实 Actions 成功且页面验证通过，才算首次自动部署完成。
