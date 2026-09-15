import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
import { readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { createRelease } from './scripts/release.mjs'

function getCommit() {
  if (process.env.GITHUB_SHA) return process.env.GITHUB_SHA
  try {
    const commit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
    const dirty = execFileSync('git', ['status', '--porcelain'], { encoding: 'utf8' }).trim()
    return dirty ? `${commit}-dirty` : commit
  } catch {
    return 'local'
  }
}

const release = createRelease(
  readFileSync(new URL('./VERSION', import.meta.url), 'utf8'),
  getCommit(),
  new Date().toISOString(),
)

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'release-metadata',
      generateBundle() {
        this.emitFile({ type: 'asset', fileName: 'release.json', source: JSON.stringify(release, null, 2) })
      },
      configureServer(server) {
        server.middlewares.use('/release.json', (_request, response) => {
          response.setHeader('Content-Type', 'application/json')
          response.setHeader('Cache-Control', 'no-store')
          response.end(JSON.stringify(release))
        })
        server.middlewares.use('/environment.json', (_request, response) => {
          response.setHeader('Content-Type', 'application/json')
          response.setHeader('Cache-Control', 'no-store')
          response.end(JSON.stringify({ environment: 'local' }))
        })
      },
    },
  ],
  define: { __RELEASE__: JSON.stringify(release) },
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
})
