interface MemoryEntry<T = string> {
  key: string;
  value: T;
  created_at: number;
  ttl_ms: number | null;
}

export class LocalMemoryProvider {
  private store = new Map<string, Map<string, MemoryEntry>>();

  remember(scope: string, key: string, value: string, ttlMs?: number): void {
    this.ensureScopeStore(scope).set(key, {
      key, value,
      created_at: Date.now(),
      ttl_ms: ttlMs || null,
    });
  }

  recall(scope: string, key: string): string | undefined {
    const entries = this.store.get(scope);
    if (!entries) return undefined;
    const entry = entries.get(key);
    if (!entry) return undefined;
    if (entry.ttl_ms && Date.now() - entry.created_at > entry.ttl_ms) {
      entries.delete(key);
      return undefined;
    }
    return entry.value;
  }

  search(scope: string, query: string): Array<{ key: string; value: string }> {
    const results: Array<{ key: string; value: string }> = [];
    const lowerQuery = query.toLowerCase();
    for (const entry of this.store.get(scope)?.values() ?? []) {
      if (entry.key.toLowerCase().includes(lowerQuery) || entry.value.toLowerCase().includes(lowerQuery)) {
        results.push({ key: entry.key, value: entry.value });
      }
    }
    return results;
  }

  forget(scope: string, key: string): boolean {
    return this.store.get(scope)?.delete(key) ?? false;
  }

  clear(scope?: string): void {
    if (scope) {
      this.store.delete(scope);
      return;
    }
    this.store.clear();
  }

  clearAll(): void {
    this.store.clear();
  }

  get size(): number {
    let total = 0;
    for (const entries of this.store.values()) total += entries.size;
    return total;
  }

  private ensureScopeStore(scope: string): Map<string, MemoryEntry> {
    const existing = this.store.get(scope);
    if (existing) return existing;
    const entries = new Map<string, MemoryEntry>();
    this.store.set(scope, entries);
    return entries;
  }
}
