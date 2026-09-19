#!/usr/bin/env python3
"""生产部署入口：固定 production 配置，复用 staging 已验证的发布和回滚逻辑。"""

from pathlib import Path
import runpy
import sys

PRODUCTION_ROOT = Path("/opt/cicd-web/environments/production")
PRODUCTION_URL = "http://127.0.0.1:18083"
shared = runpy.run_path(str(Path(__file__).with_name("deploy-staging.py")))


def deploy(archive, expected_commit, root=PRODUCTION_ROOT, base_url=PRODUCTION_URL):
    return shared["deploy"](
        archive, expected_commit, root, base_url, environment="production"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python3 deploy-production.py FRONTEND.tar.gz EXPECTED_COMMIT")
    try:
        deploy(sys.argv[1], sys.argv[2])
    except Exception as error:
        sys.exit(f"Deployment failed: {error}")
