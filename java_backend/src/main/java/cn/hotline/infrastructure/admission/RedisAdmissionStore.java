package cn.hotline.infrastructure.admission;

import cn.hotline.domain.admission.AdmissionStore;
import cn.hotline.domain.admission.AdmissionStoreUnavailableException;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

import java.time.Duration;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Supplier;

/**
 * Redis 实现：多实例共享黑名单、限流窗口、并发租约与计数台账。
 * 键前缀 hotline:admission:*；限流与并发租约使用 Lua 保证原子性；
 * 连接失败抛 {@link AdmissionStoreUnavailableException}，由上层按
 * fail-open/fail-closed 策略处理。
 */
public class RedisAdmissionStore implements AdmissionStore {

    private static final String BLACKLIST_KEY = "hotline:admission:blacklist";

    private static final DefaultRedisScript<List> RATE_SCRIPT = new DefaultRedisScript<>("""
            local count = redis.call('INCR', KEYS[1])
            if count == 1 then
                redis.call('PEXPIRE', KEYS[1], ARGV[1])
            end
            local ttl = redis.call('PTTL', KEYS[1])
            if ttl < 0 then
                ttl = tonumber(ARGV[1])
            end
            return {count, ttl}
            """, List.class);

    private static final DefaultRedisScript<Long> LEASE_SCRIPT = new DefaultRedisScript<>("""
            local now = tonumber(ARGV[1])
            redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
            if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then
                return 0
            end
            redis.call('ZADD', KEYS[1], now + tonumber(ARGV[3]), ARGV[4])
            redis.call('PEXPIRE', KEYS[1], ARGV[3])
            return 1
            """, Long.class);

    private final StringRedisTemplate template;

    public RedisAdmissionStore(StringRedisTemplate template) {
        this.template = template;
    }

    @Override
    public Set<String> blacklist() {
        Set<String> entries = execute(() -> template.opsForSet().members(BLACKLIST_KEY));
        return entries == null ? Set.of() : Set.copyOf(entries);
    }

    @Override
    public void addToBlacklist(String entry) {
        execute(() -> template.opsForSet().add(BLACKLIST_KEY, entry));
    }

    @Override
    public boolean removeFromBlacklist(String entry) {
        Long removed = execute(() -> template.opsForSet().remove(BLACKLIST_KEY, entry));
        return removed != null && removed > 0;
    }

    @Override
    public boolean isBlacklisted(String entry) {
        Boolean member = execute(() -> template.opsForSet().isMember(BLACKLIST_KEY, entry));
        return Boolean.TRUE.equals(member);
    }

    @Override
    public RateCount incrementWindow(String key, Duration window) {
        List<?> result = execute(() -> template.execute(RATE_SCRIPT,
                Collections.singletonList(key), String.valueOf(window.toMillis())));
        if (result == null || result.size() < 2) {
            throw new AdmissionStoreUnavailableException("限流脚本返回结构异常");
        }
        long count = ((Number) result.get(0)).longValue();
        long ttlMillis = ((Number) result.get(1)).longValue();
        return new RateCount(count, Duration.ofMillis(Math.max(0, ttlMillis)));
    }

    @Override
    public Optional<String> acquireLease(String key, int limit, Duration lease, String ownerId) {
        String leaseId = UUID.randomUUID().toString();
        Long acquired = execute(() -> template.execute(LEASE_SCRIPT, Collections.singletonList(key),
                String.valueOf(System.currentTimeMillis()), String.valueOf(limit),
                String.valueOf(lease.toMillis()), leaseId));
        if (acquired != null && acquired == 1L) {
            return Optional.of(leaseId);
        }
        return Optional.empty();
    }

    @Override
    public void releaseLease(String key, String leaseId) {
        execute(() -> template.opsForZSet().remove(key, leaseId));
    }

    @Override
    public long incrementCounter(String key, Duration ttl) {
        Long count = execute(() -> template.opsForValue().increment(key));
        if (count == null) {
            throw new AdmissionStoreUnavailableException("计数写入失败：" + key);
        }
        if (count == 1L) {
            execute(() -> template.expire(key, ttl));
        }
        return count;
    }

    @Override
    public long counterValue(String key) {
        String value = execute(() -> template.opsForValue().get(key));
        if (value == null) {
            return 0L;
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException exception) {
            return 0L;
        }
    }

    private <T> T execute(Supplier<T> action) {
        try {
            return action.get();
        } catch (DataAccessException exception) {
            throw new AdmissionStoreUnavailableException("Redis 治理存储不可用", exception);
        }
    }
}
