# CI/CD Lab · Frontend

React + TypeScript + Vite + Tailwind CSS + shadcn/ui 的前端版本展示页。

## 本地开发

推荐 Node.js 22。

```bash
npm ci
npm run dev
npm test
npm run build
```

开发地址 http://127.0.0.1:5173 。构建先检查 TypeScript，再生成 dist/，服务器只托管静态文件，不安装 node_modules 或执行构建。

## 版本号

只改根目录 VERSION：1.0 → 1.1 → 1.2。版本按字符串处理，1.9 后可以写 1.10。package.json 的 version 不控制页面版本。

在功能分支修改、提交、推送，再创建目标为 main 的 PR。目前只配置 CI，推送不会自动部署服务器。

## 两个学习环境

| 环境 | AWS 监听地址 | Mac 访问地址 | 容器 |
|---|---|---|---|
| 测试 | 127.0.0.1:18082 | http://127.0.0.1:18082 | cicd-web-staging |
| 生产 | 127.0.0.1:18083 | http://127.0.0.1:18083 | cicd-web-production |

主机 ubuntu@44.204.190.212，两份实例共用同一台 EC2，所以生产只是学习用的生产环境。每份 Nginx 实例内存限制 32 MB，CPU 限制为单核 10%。只绑定回环地址，通过 SSH 转发访问。

本次已经建立后台 SSH 隧道，断开后可在 Mac 重新执行并保持终端打开：

```bash
ssh -i ~/Documents/wf-2.pem -N \
  -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:18082:127.0.0.1:18082 \
  -L 127.0.0.1:18083:127.0.0.1:18083 \
  ubuntu@44.204.190.212
```

关闭本次后台隧道：

```bash
ssh -S /tmp/cicd-web.oTJaJs/ssh-control -O exit ubuntu@44.204.190.212
```

旧 Python 服务停止并取消开机启动，旧服务器发布文件仍在 /opt/cicd-lab，源码历史仍可在 Git 中查看。

## 发布数据

- /opt/cicd-web/releases/<buildId>：构建产物。
- /opt/cicd-web/environments/staging/current 和 production/current：分别指向两个环境的当前版本。
- dist/release.json：构建时记录的版本、提交、构建时间和 buildId。
- /environment.json：服务器提供的环境名和部署时间，独立于构建产物。

两个环境可部署同一份产物，不重复构建。入口 HTML、环境信息和发布记录不缓存，带哈希的资源长期缓存。

本次手动初始化包含未提交修改，提交标识带 -dirty，页面会显示“本地修改”，不冒充已提交版本。

## 当前 CI

.github/workflows/ci.yml：检出代码 → Node.js 22 → npm ci → npm test → npm run build。

当前在 feat/frontend-environments 分支，尚未代为推送或合并。推送该分支并创建 PR 才会触发这份配置的 PR 检查。

## 后续由你学习的 CD

合并 main → CI → 自动部署测试 → 人工确认 → 将同一份产物部署生产。

准确称呼是“测试环境自动部署 + 生产环境持续交付”。持续部署严格意义上指自动部署到生产环境。

ops/ 是手动部署工具，目前没有接到 GitHub Actions，也没有配置部署密钥或权限。

以下在服务器执行，BUILD_ID 要与 dist/release.json 一致：

```bash
sudo bash /opt/cicd-web/ops/deploy-static.sh /path/to/dist BUILD_ID staging
sudo bash /opt/cicd-web/ops/verify-static.sh staging BUILD_ID
# 确认测试环境后，把同一份产物部署生产：
sudo bash /opt/cicd-web/ops/deploy-static.sh /path/to/dist BUILD_ID production
# 恢复一个仍保留的历史版本：
sudo bash /opt/cicd-web/ops/rollback-static.sh staging PREVIOUS_BUILD_ID
```

## 查看或停止实验

通过 SSH 登录后执行：

```bash
sudo docker logs --tail 30 cicd-web-staging
sudo docker logs --tail 30 cicd-web-production
sudo docker update --restart=no cicd-web-staging cicd-web-production
sudo docker stop cicd-web-staging cicd-web-production
```

无需修改其他容器。不要把 SSH 私钥提交到仓库。
