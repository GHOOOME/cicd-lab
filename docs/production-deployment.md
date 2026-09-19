# CD：人工批准后部署 production

这次的目标是：staging 自动部署成功后，等待你在 GitHub 点击批准，再将同一份产物部署到 production。

```text
合并 PR 到 main
→ test：测试、构建并保存 Artifact
→ deploy_staging：自动部署测试环境
→ 等待人工批准
→ deploy_production：下载同一份 Artifact，发布生产环境
```

前提：production Environment 已设置 Required reviewers 和仅允许 main 部署。
production 内有 DEPLOY_SSH_KEY Secret，以及 DEPLOY_HOST、DEPLOY_PORT、DEPLOY_USER、DEPLOY_KNOWN_HOSTS 四个变量。
部署用户是 cicd-production，它只能写 production 部署目录，不能写 staging 部署目录。
本文不展示真实公网 IP 或私钥。

## 1. 本次准备了什么文件

已经从最新 origin/main 创建本地分支 feat/deploy-production。

- ops/deploy-staging.py：保留原 staging 用法，让内部部署函数能识别目标环境。
- ops/deploy-production.py：新增短的 production 入口，指定 production 目录和 18083 端口，复用原来的解压、版本验证、切换和失败恢复逻辑。
- ops/tests/test_deploy_staging.py：在同一组测试中补上 production 的发布、失败恢复和两环境文件独立性检查。测试只使用临时目录和本机 HTTP 服务，不连接服务器。

production 脚本需要与 deploy-staging.py 放在同一目录，下面的 Workflow 会同时上传这两个文件。
加载共享函数不会执行 staging 的命令行入口；production 调用时明确指定 production 目录与环境名。
两个环境各自保存一份相同构建文件，production 不链接到 staging 用户可修改的目录。

现有 CI 已执行 `python3 -m unittest discover -s ops/tests -v`，所以新增测试会自动被运行。
可以把这个步骤的显示名称从 `Test staging deployment script` 改为 `Test deployment scripts`，命令无需修改。

## 2. 亲自添加 production Job

编辑 .github/workflows/ci.yml，在文件末尾追加下面的 Job。
`deploy_production:` 前有两个空格，与 `test:`、`deploy_staging:` 对齐。
它不是 staging 的一个 Step，而是第三个独立 Job。

```yaml
  deploy_production:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    # staging 成功后，才轮到 production
    needs: deploy_staging
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    # 这里关联你已经设置了人工审核的 production Environment
    environment: production

    concurrency:
      group: deploy-production
      cancel-in-progress: false

    env:
      DEPLOY_HOST: ${{ vars.DEPLOY_HOST }}
      DEPLOY_PORT: ${{ vars.DEPLOY_PORT }}
      DEPLOY_USER: ${{ vars.DEPLOY_USER }}

    steps:
      - name: Checkout deployment script
        uses: actions/checkout@v7
        with:
          persist-credentials: false

      - name: Download frontend artifact
        uses: actions/download-artifact@v7
        with:
          # 与 staging 使用同一次 Workflow 的同名产物，不重新构建
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

          umask 077
          mkdir -p "$RUNNER_TEMP/production-ssh"
          printf '%s\n' "$DEPLOY_SSH_KEY" > "$RUNNER_TEMP/production-ssh/key"
          printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$RUNNER_TEMP/production-ssh/known_hosts"

          cat > "$RUNNER_TEMP/production-ssh/config" <<EOF
          Host production
            HostName $DEPLOY_HOST
            User $DEPLOY_USER
            Port $DEPLOY_PORT
            IdentityFile $RUNNER_TEMP/production-ssh/key
            UserKnownHostsFile $RUNNER_TEMP/production-ssh/known_hosts
            IdentitiesOnly yes
            BatchMode yes
            StrictHostKeyChecking yes
            ConnectTimeout 10
            ServerAliveInterval 30
            ServerAliveCountMax 3
          EOF

      - name: Upload and deploy production
        run: |
          ssh_config="$RUNNER_TEMP/production-ssh/config"
          upload_id="${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"

          tar -czf "$RUNNER_TEMP/frontend.tar.gz" -C dist .
          ssh -F "$ssh_config" production "mkdir -p incoming/$upload_id"
          # 两个 Python 文件要一起上传，production 入口会加载共享逻辑
          scp -F "$ssh_config" \
            "$RUNNER_TEMP/frontend.tar.gz" \
            ops/deploy-staging.py \
            ops/deploy-production.py \
            "production:incoming/$upload_id/"

          ssh -F "$ssh_config" production \
            "trap 'rm -rf -- incoming/$upload_id' EXIT; python3 incoming/$upload_id/deploy-production.py incoming/$upload_id/frontend.tar.gz '$GITHUB_SHA'"

      - name: Clean up local SSH files
        if: always()
        run: |
          rm -rf -- "$RUNNER_TEMP/production-ssh"
          rm -f -- "$RUNNER_TEMP/frontend.tar.gz"
```

这一段与 staging 的主要区别：

| 设置 | staging | production |
|---|---|---|
| 等谁先成功 | needs: test | needs: deploy_staging |
| 使用哪个 GitHub 环境 | environment: staging | environment: production |
| 登录服务器的账号 | cicd-staging | cicd-production |
| 运行哪个入口 | deploy-staging.py | deploy-production.py |
| 是否人工批准 | 不需要 | 由 production Environment 的 Required reviewers 决定 |

`needs` 只负责等待前一个 Job 成功；人工批准来自 Environment 的审核规则。
仅写 `environment: production` 而没有配置 Required reviewers，不会自动产生人工审核。
这里的 10 分钟限制针对 Job 执行，不是要求审核人必须在 10 分钟内点击批准。

## 3. 改版本，提交 PR

将 VERSION 从 1.1 改为 1.2，便于看清这次实验各阶段的差别。
在 Mac 的项目终端执行：

```bash
git status
git diff
git add .github/workflows/ci.yml VERSION ops/deploy-staging.py ops/deploy-production.py ops/tests/test_deploy_staging.py docs/production-deployment.md
git commit -m "ci: promote tested frontend to production after approval"
git push -u origin feat/deploy-production
```

在 GitHub 创建目标为 main 的 PR。PR 阶段应看到 test 成功，两个部署 Job 都跳过。
确认后合并 PR，打开 Actions 中这次 main push 的运行详情。

## 4. 观察等待批准，然后批准

这次实验先只合并这一条 PR，便于观察同一版本的完整过程。
staging 成功后，运行应显示等待生产环境审核。
此时 staging 页面应是 1.2，production 页面仍为 1.0。

批准入口：仓库 → Actions → 这一次运行 → Review deployments → 勾选 production → Approve and deploy。

不要使用 Start all waiting jobs 等绕过审批的入口；本实验要体验正常审批。
点击批准后，生产 Job 才能继续并获得 production 环境里的 Secret。
如果没有等待就直接部署，先检查 production Environment 是否保存了 Required reviewers。

## 5. 怎样才算成功

部署成功后，应看到 deploy_production 绿色成功；服务日志中有 `Deployed production: 1.2`。
通过已经建立的管理员 SSH 隧道访问 http://127.0.0.1:18083，刷新页面，应显示 production 和 1.2。
staging 使用 http://127.0.0.1:18082，仍显示 staging 和 1.2。
两个环境的 release.json 应有相同的 commit、buildId 和 builtAt，证明使用同一份构建产物；
各自 environment.json 的环境名和部署时间可以不同。

如果本地地址打不开，先检查 Mac 的 SSH 隧道是否连接，不要据此认定服务器部署失败。

## 审批到底发布哪个版本

批准针对的是你打开的那一次 Workflow 运行，它发布那一次运行的 Artifact。
它不会自动换成批准时 main 的最新代码。审批前检查运行的提交 SHA 和版本。
如果同时存在多次等待批准的运行，不要随意批准旧运行，否则旧版本也可能被发布。
我们当前的并发控制只防止同组部署重叠，不会自动拒绝旧版本。

Artifact 当前保存 7 天，请在产物仍可下载时完成审批；过期后应重新产生并验证产物。

官方说明：[审查部署](https://docs.github.com/zh/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments)。
