interface MemoryEntry<T = string> {
  key: string;
  value: T;
  created_at: number;
  ttl_ms: number | null;
}

export class LocalMemoryProvider {
  private store = new Map<string, MemoryEntry>();

  remember(key: string, value: string, ttlMs?: number): void {
    this.store.set(key, {
      key, value,
      created_at: Date.now(),
      ttl_ms: ttlMs || null,
    });
  }

  recall(key: string): string | undefined {
    const entry = this.store.get(key);
    if (!entry) return undefined;
    if (entry.ttl_ms && Date.now() - entry.created_at > entry.ttl_ms) {
      this.store.delete(key);
      return undefined;
    }
    return entry.value;
  }

  search(query: string): Array<{ key: string; value: string }> {
    const results: Array<{ key: string; value: string }> = [];
    const lowerQuery = query.toLowerCase();
    for (const entry of this.store.values()) {
      if (entry.key.toLowerCase().includes(lowerQuery) || entry.value.toLowerCase().includes(lowerQuery)) {
        results.push({ key: entry.key, value: entry.value });
      }
    }
    return results;
  }

  forget(key: string): boolean {
    return this.store.delete(key);
  }

  clear(): void {
    this.store.clear();
  }

  get size(): number {
    return this.store.size;
  }
}
