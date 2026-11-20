const STORAGE_VERSION = 1

type StoredValue<T> = {
  version: number
  value: T
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function readStored<T>(key: string, fallback: T, isValid?: (value: unknown) => value is T): T {
  if (typeof window === 'undefined') return fallback

  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return fallback
    const parsed: unknown = JSON.parse(raw)
    const candidate = isRecord(parsed) && 'version' in parsed && 'value' in parsed
      ? (parsed as StoredValue<unknown>).value
      : parsed
    return !isValid || isValid(candidate) ? candidate as T : fallback
  } catch (error) {
    console.error(`Could not read ${key} from browser storage.`, error)
    return fallback
  }
}

export function writeStored<T>(key: string, value: T): boolean {
  if (typeof window === 'undefined') return false

  try {
    const envelope: StoredValue<T> = { version: STORAGE_VERSION, value }
    window.localStorage.setItem(key, JSON.stringify(envelope))
    return true
  } catch (error) {
    console.error(`Could not save ${key} to browser storage.`, error)
    return false
  }
}

export function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean'
}

export function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every(item => Number.isSafeInteger(item))
}

export function isArrayOf<T>(isItem: (value: unknown) => value is T) {
  return (value: unknown): value is T[] => Array.isArray(value) && value.every(isItem)
}
