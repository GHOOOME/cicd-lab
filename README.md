# CI/CD Lab

用于学习 CI 和 AWS 部署的最小 HTTP API。只依赖 Python 3 标准库，没有数据库或第三方包。

## 本地运行与测试

```bash
python3 -m unittest discover -s tests -v
python3 server.py
```

默认监听 `127.0.0.1:18081`。`/` 返回服务信息，`/health` 返回健康状态，`/version` 返回 `VERSION` 文件中的发布版本。未知路径返回 404，不提供目录或源码下载。

## 本次 AWS 部署

- 主机：`ubuntu@44.204.190.212`，AWS EC2 `t3.small`。
- 发布目录：`/opt/cicd-lab/releases/0.1.0`。
- 当前版本：`/opt/cicd-lab/current` 符号链接。
- 服务：`cicd-lab.service`，由 systemd 管理并在开机时启动。
- 监听地址：服务器的 `127.0.0.1:18081`，通过 SSH 隧道访问。
- 资源限制：64 MB 内存、禁止使用 swap、最多占用单个 CPU 核心的 10%。

这个示例使用 Python 标准库 HTTP 服务器，仅用于学习实验。内存和 CPU 限制作用于示例服务，不保证整台共享主机的业务资源隔离。

## 从 Mac 访问

在需要新建隧道时执行下面的命令，并保持该终端打开。已有隧道时无需重复执行。

```bash
ssh -i ~/Documents/wf-2.pem -N \
  -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:18081:127.0.0.1:18081 ubuntu@44.204.190.212
```

随后访问 `http://127.0.0.1:18081/health`。地址虽然是本地地址，但请求经 SSH 转发到 AWS。直接访问服务器公网 IP 的 18081 端口不会连接到这个服务。

本次已经建立了后台 SSH 隧道。只关闭本次隧道而保留远端服务，可以在 Mac 上执行：

```bash
ssh -S /tmp/cicd-lab.BdrhFB/ssh-control -O exit ubuntu@44.204.190.212
```

隧道断开或 Mac 重启后，可以使用上面的前台转发命令重新连接。服务器上的 systemd 服务独立运行，不依赖 Mac 保持连接。

## 管理服务

先通过 SSH 登录服务器：

```bash
ssh -i ~/Documents/wf-2.pem ubuntu@44.204.190.212
```

在服务器上执行：

```bash
sudo systemctl status cicd-lab --no-pager
sudo journalctl -u cicd-lab -n 30 --no-pager
curl -fsS http://127.0.0.1:18081/health
```

结束实验时，下面的命令只停止示例服务并取消其开机启动，保留文件：

```bash
sudo systemctl disable --now cicd-lab
```

## 下一步：GitHub Actions

`.github/workflows/ci.yml` 已准备好：检出代码、设置 Python、执行接口测试。目前没有创建或推送 GitHub 仓库，也没有执行过远程 Actions 工作流；此次部署属于手动部署。

将此项目单独放入自己的 GitHub 仓库后，可以练习 PR 自动测试、故意让测试失败再修复。随后再设计自动部署、版本更新和回滚。SSH 私钥不属于项目文件，不能上传到仓库。
