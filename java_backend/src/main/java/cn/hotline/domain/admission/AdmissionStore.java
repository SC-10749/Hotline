package cn.hotline.domain.admission;

import java.time.Duration;
import java.util.Optional;
import java.util.Set;

/**
 * 接入治理存储：黑名单、限流窗口、并发租约与计数台账。
 * 内存实现用于单机本地，Redis 实现用于多实例共享；存储故障抛
 * {@link AdmissionStoreUnavailableException}，由上层按 fail-open/fail-closed 策略处理。
 */
public interface AdmissionStore {

    Set<String> blacklist();

    void addToBlacklist(String entry);

    boolean removeFromBlacklist(String entry);

    boolean isBlacklisted(String entry);

    /** 固定窗口计数：窗口内首次调用开始计时，返回当前计数与建议的重试等待时长。 */
    RateCount incrementWindow(String key, Duration window);

    /** 申请并发租约：达到上限返回空。 */
    Optional<String> acquireLease(String key, int limit, Duration lease, String ownerId);

    void releaseLease(String key, String leaseId);

    /** 自增计数（台账/配额），首次自增时设置过期时间。 */
    long incrementCounter(String key, Duration ttl);

    /** 读取计数（不存在或已过期返回 0）。 */
    long counterValue(String key);

    /** 固定窗口计数结果。 */
    record RateCount(long count, Duration retryAfter) {
    }
}
