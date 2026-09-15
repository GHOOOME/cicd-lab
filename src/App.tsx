import { useEffect, useState } from 'react'
import { ArrowUpRight, Check, Copy, FlaskConical, GitCommitHorizontal, Layers2, RefreshCw, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { environments, parseEnvironment, type EnvironmentInfo } from '@/lib/environment'

const release = __RELEASE__

function formatTime(value?: string) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium', timeStyle: 'short', hour12: false,
  }).format(new Date(value))
}

export default function App() {
  const [info, setInfo] = useState<EnvironmentInfo | null>(null)
  const [error, setError] = useState(false)
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    const timer = window.setTimeout(() => controller.abort(), 8000)
    fetch('/environment.json', { cache: 'no-store', signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error('Environment request failed')
        return response.json()
      })
      .then(data => { if (!disposed) { setInfo(parseEnvironment(data)); setError(false) } })
      .catch(() => { if (!disposed) setError(true) })
      .finally(() => window.clearTimeout(timer))
    return () => { disposed = true; window.clearTimeout(timer); controller.abort() }
  }, [])

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 2000)
    return () => window.clearTimeout(timer)
  }, [copied])

  const environment = info ? environments[info.environment] : null
  const EnvironmentIcon = info?.environment === 'production' ? ShieldCheck : FlaskConical
  const isDirty = release.commit.endsWith('-dirty')
  const shortCommit = release.commit === 'local' ? 'local' : release.commit.slice(0, 7)

  async function copyVersion() {
    try {
      await navigator.clipboard.writeText(release.version)
      setCopied(true)
      setCopyError(false)
    } catch {
      setCopyError(true)
    }
  }

  return (
    <TooltipProvider>
      <div className="app-shell" data-environment={info?.environment ?? 'unknown'}>
        <header className="topbar">
          <a href="/" className="brand" aria-label="CI/CD Lab 首页">
            <span className="brand-symbol"><Layers2 size={20} strokeWidth={1.7} /></span>
            <span>CI/CD Lab<span className="brand-suffix"> / Release</span></span>
          </a>
          <div className="header-actions">
            <Badge variant="outline" className="environment-badge">
              {environment ? <><EnvironmentIcon size={13} />{environment.name}</> : error ? '环境未知' : '读取环境…'}
            </Badge>
            <Separator orientation="vertical" className="header-divider" />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" asChild>
                  <a href="https://github.com/GHOOOME/cicd-lab" target="_blank" rel="noreferrer" aria-label="打开 GitHub 仓库">
                    <img src="/github-mark.png" width="21" height="21" alt="" />
                  </a>
                </Button>
              </TooltipTrigger>
              <TooltipContent>GitHub 仓库</TooltipContent>
            </Tooltip>
          </div>
        </header>

        <main className="release-main">
          <div className="release-summary">
            <div className="environment-title"><EnvironmentIcon size={17} /><span>{environment?.label ?? 'Environment'}</span></div>
            <p className="version-label">当前版本</p>
            <div className="version-line">
              <span className="version-prefix" aria-hidden="true">v</span>
              <h1 data-testid="release-version" aria-label={`当前版本 ${release.version}`}>{release.version}</h1>
            </div>
            <div className="release-state" role="status">
              <span className={error ? 'status-dot status-error' : info ? 'status-dot' : 'status-dot status-loading'} />
              {error ? '无法读取环境信息' : info ? info.environment === 'local' ? '本地预览' : '当前部署' : '正在读取环境信息'}
            </div>
            <div className="release-actions">
              <Button variant="outline" onClick={() => window.location.reload()}>
                <RefreshCw size={15} />刷新页面
              </Button>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" onClick={copyVersion} aria-label={copied ? '版本号已复制' : '复制版本号'}>
                    {copied ? <Check size={16} /> : <Copy size={16} />}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{copied ? '已复制' : '复制版本号'}</TooltipContent>
              </Tooltip>
            </div>
            <p className="copy-feedback" aria-live="polite">{copyError ? `无法自动复制，版本号：${release.version}` : copied ? '版本号已复制' : '\u00a0'}</p>
          </div>

          <section className="release-details" aria-label="发布信息">
            <div className="details-heading"><span>发布信息</span><Badge variant="secondary">{environment?.name ?? '环境未确认'}</Badge></div>
            <Separator />
            <dl>
              <div className="detail-row"><dt>代码提交</dt><dd className="commit-value"><GitCommitHorizontal size={16} /><code>{shortCommit}</code>{isDirty && <span className="dirty-label">本地修改</span>}</dd></div>
              <div className="detail-row"><dt>构建时间</dt><dd>{formatTime(release.builtAt)}</dd></div>
              <div className="detail-row"><dt>部署时间</dt><dd>{info?.environment === 'local' ? '本地开发' : formatTime(info?.deployedAt)}</dd></div>
              <div className="detail-row"><dt>环境端口</dt><dd><code>{environment?.port ?? '—'}</code></dd></div>
            </dl>
          </section>
        </main>

        <footer className="footer">
          <span className="footer-product"><Layers2 size={14} />CI/CD Lab</span>
          <span className="footer-center">{info?.environment === 'local' ? 'Local workspace' : info ? 'Amazon EC2' : '—'}</span>
          <a href="/release.json" target="_blank" rel="noreferrer">构建记录<ArrowUpRight size={13} /></a>
        </footer>
      </div>
    </TooltipProvider>
  )
}
