import { describe, expect, it } from 'vitest'
import { parseEnvironment } from './environment'
import { validateVersion } from '../../scripts/release.mjs'

describe('deployment identity', () => {
  it.each(['staging', 'production', 'local'])('accepts %s environment', environment => {
    expect(parseEnvironment({ environment }).environment).toBe(environment)
  })
  it.each([null, {}, { environment: 'preview' }, { environment: 'production', deployedAt: 'bad' }])(
    'rejects invalid metadata instead of implying production is healthy: %j', value => {
      expect(() => parseEnvironment(value)).toThrow()
    },
  )
  it('keeps decimal versions as strings', () => {
    expect(validateVersion('1.10\n')).toBe('1.10')
  })
  it('rejects malformed release versions', () => {
    expect(() => validateVersion('1.0<script>')).toThrow()
  })
})
