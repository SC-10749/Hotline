package cn.hotline.infrastructure.config;

import cn.hotline.domain.admission.AdmissionStore;
import cn.hotline.infrastructure.admission.InMemoryAdmissionStore;
import cn.hotline.infrastructure.admission.RedisAdmissionStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionCommands;
import org.springframework.data.redis.core.StringRedisTemplate;

/**
 * 接入治理装配：按配置选择内存或 Redis 存储。
 * auto 模式启动时探测 Redis，不可用则回退内存并告警；
 * redis 模式启动时探测失败直接报错（fail-fast，避免误以为已共享治理状态）。
 */
@Configuration
public class AdmissionConfiguration {

    private static final Logger log = LoggerFactory.getLogger(AdmissionConfiguration.class);

    @Bean
    public AdmissionStore admissionStore(AdmissionProperties properties,
                                         ObjectProvider<StringRedisTemplate> redisTemplateProvider) {
        if (properties.store() == AdmissionProperties.Store.MEMORY) {
            log.info("接入治理存储：内存（单实例）");
            return new InMemoryAdmissionStore();
        }
        StringRedisTemplate template = redisTemplateProvider.getIfAvailable();
        boolean redisReachable = template != null && ping(template);
        if (redisReachable) {
            log.info("接入治理存储：Redis");
            return new RedisAdmissionStore(template);
        }
        if (properties.store() == AdmissionProperties.Store.REDIS) {
            throw new IllegalStateException("hotline.admission.store=redis 但 Redis 不可用，请检查 spring.data.redis 配置");
        }
        log.warn("接入治理未探测到可用 Redis，回退内存存储（单实例）");
        return new InMemoryAdmissionStore();
    }

    private boolean ping(StringRedisTemplate template) {
        try {
            return "PONG".equalsIgnoreCase(template.execute(RedisConnectionCommands::ping));
        } catch (Exception exception) {
            log.debug("Redis 探测失败：{}", exception.getMessage());
            return false;
        }
    }
}
