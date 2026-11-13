package cn.hotline.application.admission;

import cn.hotline.domain.admission.AdmissionStore;
import cn.hotline.domain.admission.AdmissionStoreUnavailableException;
import cn.hotline.infrastructure.config.AdmissionProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.LocalDate;

/**
 * 提交台账：按客户端统计当日提交次数，供 hotline.admission.submission-quota-per-day
 * 配额检查使用。计数器键含业务日期做天然滚动，TTL 26 小时兜底清理；
 * 存储故障时按 redis-fail-open 决定放行或抛出。
 */
@Service
public class SubmissionLedger {

    private static final Logger log = LoggerFactory.getLogger(SubmissionLedger.class);
    private static final Duration COUNTER_TTL = Duration.ofHours(26);
    private static final String KEY_PREFIX = "hotline:admission:submission:";

    private final AdmissionStore admissionStore;
    private final AdmissionProperties properties;

    public SubmissionLedger(AdmissionStore admissionStore, AdmissionProperties properties) {
        this.admissionStore = admissionStore;
        this.properties = properties;
    }

    /** 是否已达当日配额（quota<=0 表示不限额）。 */
    public boolean exceeded(String clientKey, long quota) {
        if (quota <= 0) {
            return false;
        }
        try {
            return admissionStore.counterValue(counterKey(clientKey)) >= quota;
        } catch (AdmissionStoreUnavailableException exception) {
            if (properties.redisFailOpen()) {
                log.warn("提交台账存储不可用，按 fail-open 放行：{}", exception.getMessage());
                return false;
            }
            throw exception;
        }
    }

    /** 记一次提交（尽力而为，失败仅告警——不阻断已受理的提交）。 */
    public void record(String clientKey) {
        try {
            admissionStore.incrementCounter(counterKey(clientKey), COUNTER_TTL);
        } catch (AdmissionStoreUnavailableException exception) {
            log.warn("提交台账记录失败：{}", exception.getMessage());
        }
    }

    private String counterKey(String clientKey) {
        return KEY_PREFIX + LocalDate.now() + ":" + clientKey;
    }
}
