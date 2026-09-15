import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

describe('release screen', () => {
  it('displays the compiled version with the server environment', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ environment: 'staging', deployedAt: '2026-09-15T00:00:00Z' }),
    }))
    render(<App />)
    expect(screen.getByTestId('release-version')).toHaveTextContent(__RELEASE__.version)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('当前部署'))
    expect(screen.getByText('Staging')).toBeInTheDocument()
    expect(screen.getByText('18082')).toBeInTheDocument()
  })

  it('does not pretend to be a deployed environment when metadata is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    render(<App />)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('无法读取环境信息'))
    expect(screen.queryByText('当前部署')).not.toBeInTheDocument()
    expect(screen.getByText('环境未知')).toBeInTheDocument()
  })
})
