package cn.hotline.infrastructure.admission;

import cn.hotline.domain.admission.AdmissionStore;

import java.time.Clock;
import java.time.Duration;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 内存实现：单机部署默认。黑名单、固定窗口计数、并发租约与计数器均保存在进程内存，
 * 多实例部署需要切换 Redis 实现共享状态。
 */
public class InMemoryAdmissionStore implements AdmissionStore {

    private final Clock clock;
    private final Set<String> blacklist = ConcurrentHashMap.newKeySet();
    private final Map<String, RateWindow> windows = new ConcurrentHashMap<>();
    private final Map<String, Map<String, Long>> leaseGroups = new ConcurrentHashMap<>();
    private final Map<String, Counter> counters = new ConcurrentHashMap<>();

    public InMemoryAdmissionStore() {
        this(Clock.systemUTC());
    }

    public InMemoryAdmissionStore(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Set<String> blacklist() {
        return Set.copyOf(blacklist);
    }

    @Override
    public void addToBlacklist(String entry) {
        blacklist.add(entry);
    }

    @Override
    public boolean removeFromBlacklist(String entry) {
        return blacklist.remove(entry);
    }

    @Override
    public boolean isBlacklisted(String entry) {
        return blacklist.contains(entry);
    }

    @Override
    public RateCount incrementWindow(String key, Duration window) {
        long now = clock.millis();
        RateWindow current = windows.compute(key, (ignored, existing) -> {
            if (existing == null || now - existing.startMillis() >= window.toMillis()) {
                return new RateWindow(now, new AtomicLong(1));
            }
            existing.count().incrementAndGet();
            return existing;
        });
        long remaining = Math.max(0, window.toMillis() - (now - current.startMillis()));
        return new RateCount(current.count().get(), Duration.ofMillis(remaining));
    }

    @Override
    public Optional<String> acquireLease(String key, int limit, Duration lease, String ownerId) {
        long now = clock.millis();
        Map<String, Long> leases = leaseGroups.computeIfAbsent(key, ignored -> new ConcurrentHashMap<>());
        synchronized (leases) {
            leases.entrySet().removeIf(entry -> entry.getValue() <= now);
            if (leases.size() >= limit) {
                return Optional.empty();
            }
            String leaseId = UUID.randomUUID().toString();
            leases.put(leaseId, now + lease.toMillis());
            return Optional.of(leaseId);
        }
    }

    @Override
    public void releaseLease(String key, String leaseId) {
        Map<String, Long> leases = leaseGroups.get(key);
        if (leases != null) {
            leases.remove(leaseId);
        }
    }

    @Override
    public long incrementCounter(String key, Duration ttl) {
        long now = clock.millis();
        Counter counter = counters.compute(key, (ignored, existing) -> {
            if (existing == null || existing.expiresAtMillis() <= now) {
                return new Counter(new AtomicLong(1), now + ttl.toMillis());
            }
            existing.value().incrementAndGet();
            return existing;
        });
        return counter.value().get();
    }

    @Override
    public long counterValue(String key) {
        Counter counter = counters.get(key);
        if (counter == null || counter.expiresAtMillis() <= clock.millis()) {
            return 0L;
        }
        return counter.value().get();
    }

    private record RateWindow(long startMillis, AtomicLong count) {
    }

    private record Counter(AtomicLong value, long expiresAtMillis) {
    }
}
