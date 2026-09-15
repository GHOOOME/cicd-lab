export function validateVersion(value) {
  const version = value.trim()
  if (!/^\d+\.\d+(?:\.\d+)?$/.test(version)) {
    throw new Error('VERSION must contain a version such as 1.0 or 1.1')
  }
  return version
}

export function createRelease(version, commit, builtAt) {
  const buildId = `${commit.slice(0, 7)}-${builtAt.replace(/[^0-9]/g, '')}`
  return { version: validateVersion(version), commit, builtAt, buildId }
}
