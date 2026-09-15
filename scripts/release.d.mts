export function validateVersion(value: string): string
export function createRelease(version: string, commit: string, builtAt: string): {
  version: string
  commit: string
  builtAt: string
  buildId: string
}
