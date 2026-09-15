export const environments = {
  local: { name: '本地开发', label: 'Local', port: '5173', tone: 'local' },
  staging: { name: '测试环境', label: 'Staging', port: '18082', tone: 'staging' },
  production: { name: '生产环境', label: 'Production', port: '18083', tone: 'production' },
} as const

export type EnvironmentName = keyof typeof environments
export type EnvironmentInfo = { environment: EnvironmentName; deployedAt?: string }

export function parseEnvironment(value: unknown): EnvironmentInfo {
  if (typeof value !== 'object' || value === null || !('environment' in value)) {
    throw new Error('环境信息格式错误')
  }
  if (value.environment !== 'local' && value.environment !== 'staging' && value.environment !== 'production') {
    throw new Error('未知环境')
  }
  if ('deployedAt' in value && value.deployedAt !== undefined &&
      (typeof value.deployedAt !== 'string' || Number.isNaN(Date.parse(value.deployedAt)))) {
    throw new Error('部署时间格式错误')
  }
  return {
    environment: value.environment,
    deployedAt: 'deployedAt' in value ? value.deployedAt as string | undefined : undefined,
  }
}
